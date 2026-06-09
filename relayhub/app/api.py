"""FastAPI 路由 (技术文档 B5)。承载原型 UI, 仅监听 127.0.0.1 (SEC-3)。

启动: uvicorn app.api:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import base64
import re
import secrets
import threading
import time
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response

from .alerts import AlertService
from .config import load_settings
from .health import HealthChecker
from .marzban import MarzbanClient, MarzbanError
from .models import LineSpec
from .notify import TelegramNotifier
from .provisioning import ProvisioningService

app = FastAPI(title="RelayHub", version="0.1.0")

_settings = load_settings()
_service = ProvisioningService(MarzbanClient(_settings), _settings)
_checker = HealthChecker()
_notifier = TelegramNotifier(_settings.telegram_bot_token, _settings.telegram_chat_id)
_alerts = AlertService(_service, _settings, _notifier, _checker)


def _alert_loop():
    interval = max(60, _settings.alert_interval_min * 60)
    while True:
        try:
            _alerts.run_once()
        except Exception:                  # noqa: BLE001 — 后台循环不因单次失败退出
            pass
        time.sleep(interval)


@app.on_event("startup")
def _start_scheduler():
    if _settings.alert_interval_min > 0 and _notifier.enabled:
        threading.Thread(target=_alert_loop, daemon=True).start()


@app.middleware("http")
async def _basic_auth(request: Request, call_next):
    """面板登录鉴权: 配了 panel_password 才启用 (公网开放时必配)。"""
    pw = _settings.panel_password
    if pw and not request.url.path.startswith("/sub"):   # 订阅必须公开, 豁免鉴权
        hdr = request.headers.get("authorization", "")
        ok = False
        if hdr.startswith("Basic "):
            try:
                user, _, passwd = base64.b64decode(hdr[6:]).decode().partition(":")
                ok = (secrets.compare_digest(user, _settings.panel_user)
                      and secrets.compare_digest(passwd, pw))
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            return Response(status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="RelayHub"'})
    return await call_next(request)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _err(code: int, message: str):
    return JSONResponse(status_code=code, content={"error": {"code": code, "message": message}})


@app.exception_handler(MarzbanError)
async def _marzban_err(_, exc: MarzbanError):
    return _err(502, str(exc))


@app.exception_handler(ValueError)
async def _value_err(_, exc: ValueError):
    return _err(400, str(exc))


@app.exception_handler(RequestValidationError)
async def _validation_err(_, exc: RequestValidationError):
    for e in exc.errors():
        if "name" in e.get("loc", []):
            return _err(422, "客户名只能用英文字母/数字/下划线, 长度 2-32 位 (不能用中文)")
    return _err(422, "参数校验失败: " + "; ".join(
        f"{'.'.join(str(x) for x in e.get('loc', []))}: {e.get('msg', '')}" for e in exc.errors()))


@app.get("/")
def index():
    idx = WEB_DIR / "index.html"
    if not idx.exists():
        raise HTTPException(404, "index.html not found")
    return FileResponse(idx)


_SUB_PASSTHRU_HEADERS = {
    "profile-title", "profile-update-interval", "subscription-userinfo",
    "content-disposition", "profile-web-page-url", "support-url",
}

# 大流量机场节点缓存 (避免每次订阅请求都拉机场)
_highvol_cache: dict = {"t": 0.0, "proxies": []}
_INFO_NODE_MARKERS = ("流量", "到期", "剩余", "过期", "重置", "官网", "网址",
                      "客服", "订阅", "www.", "http", "telegram", "群组")


def _is_real_node(name: str) -> bool:
    return bool(name) and not any(m in name for m in _INFO_NODE_MARKERS)


def _highvol_proxies() -> list:
    """拉取大流量机场的节点 (缓存 30 分钟; 出错用旧缓存)。"""
    url = _settings.highvol_sub_url
    if not url:
        return []
    if time.time() - _highvol_cache["t"] < 1800 and _highvol_cache["proxies"]:
        return _highvol_cache["proxies"]
    try:
        with httpx.Client(verify=False, timeout=20.0) as c:
            r = c.get(url, headers={"user-agent": "clash.meta"})
        d = yaml.safe_load(r.text)
        ps = [p for p in (d.get("proxies") or []) if _is_real_node(p.get("name", ""))]
        if ps:
            _highvol_cache["t"] = time.time()
            _highvol_cache["proxies"] = ps
    except Exception:  # noqa: BLE001
        pass
    return _highvol_cache["proxies"]


def _build_split_sub(text: str, exit_ip: str | None) -> bytes:
    """把机场节点合并进 clash 订阅: AI专线=本节点(带出口IP), 大流量=机场节点。"""
    d = yaml.safe_load(text)
    our = d.get("proxies") or []
    our_names = []
    for p in our:                                     # 本节点名带上出口IP
        nm = p.get("name", "")
        if exit_ip and exit_ip not in nm:
            nm = f"{nm} · {exit_ip}"
            p["name"] = nm
        our_names.append(nm)
    air = _highvol_proxies()
    air_names = [p.get("name") for p in air]
    d["proxies"] = our + air
    groups = d.get("proxy-groups") or []
    auto = {"name": "🚀 大流量-自动", "type": "url-test",
            "url": "http://www.gstatic.com/generate_204", "interval": 300,
            "tolerance": 80, "proxies": air_names or ["DIRECT"]}
    for g in groups:
        if g.get("name") == "🤖 AI 专线":
            g["proxies"] = our_names or ["DIRECT"]
        elif g.get("name") == "🚀 大流量":
            g["proxies"] = (["🚀 大流量-自动"] + air_names) if air_names else ["DIRECT"]
    if air_names:
        groups.insert(0, auto)
    d["proxy-groups"] = groups
    return yaml.dump(d, allow_unicode=True, sort_keys=False).encode("utf-8")


def _inject_exit_ip(body: bytes, ip: str) -> bytes:
    """把出口 IP 追加到 clash 节点名 (仅 proxies 段内的节点, 全局一致替换)。失败原样返回。"""
    try:
        text = body.decode("utf-8")
        m = re.search(r"\nproxies:\s*\n(.*?)\n(?:proxy-groups|rules):", text, re.S)
        if not m:
            return body
        names = re.findall(r"^\s*-?\s*name:\s*(.+?)\s*$", m.group(1), re.M)
        for nm in names:
            nm = nm.strip().strip('"').strip("'")
            if nm and ip not in nm:
                text = text.replace(nm, f"{nm} · {ip}")
        return text.encode("utf-8")
    except Exception:  # noqa: BLE001
        return body


@app.get("/sub/{token}")
def subscription(token: str, request: Request):
    """中转 Marzban 订阅, 并把开通时探测到的 decode 出口 IP 注入节点名。

    任何环节出错都回落为 Marzban 原样输出, 不影响订阅可用性。
    """
    ua = request.headers.get("user-agent", "")
    base = _settings.marzban_url.rstrip("/")
    try:
        with httpx.Client(verify=_settings.verify_tls, timeout=20.0) as cli:
            r = cli.get(f"{base}/sub/{token}", headers={"user-agent": ua})
            body = r.content
            ctype = r.headers.get("content-type", "text/plain")
            headers = {k: v for k, v in r.headers.items()
                       if k.lower() in _SUB_PASSTHRU_HEADERS}
            if b"proxies:" in body:                     # 仅 clash/meta 才处理
                try:
                    info = cli.get(f"{base}/sub/{token}/info",
                                   headers={"user-agent": ua}).json()
                    username = info.get("username")
                    note = _service.client.get_user(username).get("note") or "" if username else ""
                    mip = re.search(r"exit_ip=([0-9.]+)", note)
                    exit_ip = mip.group(1) if mip else None
                    if _settings.highvol_sub_url:        # 分流模式: 合并机场节点
                        body = _build_split_sub(body.decode("utf-8", "ignore"), exit_ip)
                    elif exit_ip:                        # 普通模式: 只注入出口IP
                        body = _inject_exit_ip(body, exit_ip)
                except Exception:  # noqa: BLE001
                    pass
            return Response(content=body, status_code=r.status_code,
                            media_type=ctype, headers=headers)
    except httpx.HTTPError:
        raise HTTPException(502, "subscription upstream error")


@app.post("/api/lines")
def create_line(spec: LineSpec):
    return _service.provision(spec)


@app.get("/api/lines")
def list_lines():
    return _service.list_customers()


@app.get("/api/stats")
def stats():
    customers = _service.list_customers()
    online = sum(1 for c in customers if c.status == "ok")
    used = round(sum(c.used_gb for c in customers), 1)
    expiring = sum(1 for c in customers if c.expire.endswith("天") and _days(c.expire) <= 7)
    return {
        "customers": len(customers),
        "online": online,
        "used_gb": used,
        "expiring": expiring,
    }


@app.get("/api/health")
def health():
    """对每条 decode 线路做真实探活, 返回延迟与出口 IP (P5)。"""
    return _checker.check_many(_service.line_endpoints())


@app.get("/api/alerts")
def alerts():
    """当前告警预览 (到期/流量/线路), 不推送 (P5)。"""
    return _alerts.current()


@app.post("/api/lines/{name}/rotate-sub")
def rotate_sub(name: str):
    return {"sub_url": _service.rotate_sub(name)}


@app.delete("/api/lines/{name}", status_code=204)
def delete_line(name: str):
    _service.remove(name)


def _days(expire: str) -> int:
    try:
        return int(expire.replace("天", "").strip())
    except ValueError:
        return 999
