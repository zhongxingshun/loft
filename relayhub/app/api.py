"""FastAPI 路由 (技术文档 B5)。承载原型 UI, 仅监听 127.0.0.1 (SEC-3)。

启动: uvicorn app.api:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse

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

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _err(code: int, message: str):
    return JSONResponse(status_code=code, content={"error": {"code": code, "message": message}})


@app.exception_handler(MarzbanError)
async def _marzban_err(_, exc: MarzbanError):
    return _err(502, str(exc))


@app.exception_handler(ValueError)
async def _value_err(_, exc: ValueError):
    return _err(400, str(exc))


@app.get("/")
def index():
    idx = WEB_DIR / "index.html"
    if not idx.exists():
        raise HTTPException(404, "index.html not found")
    return FileResponse(idx)


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
