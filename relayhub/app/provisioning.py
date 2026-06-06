"""开通编排服务 (技术文档 B4.5)。

ProvisioningService 是唯一编排者: CLI 与 Web 都经它, 保证安全护栏不可旁路。
core config 的读-改-写以进程锁串行化, 防并发覆盖。
"""
from __future__ import annotations

import threading
import time

from . import guard
from .config import Settings
from .models import CustomerView, LineSpec, ProvisionResult, SocksEndpoint
from .parsing import parse_socks

_GB = 1024 ** 3


def make_outbound(out_tag: str, sock: SocksEndpoint) -> dict:
    server: dict = {"address": sock.address, "port": sock.port}
    if sock.user:
        server["users"] = [{"user": sock.user, "pass": sock.password}]
    return {"tag": out_tag, "protocol": "socks", "settings": {"servers": [server]}}


class ProvisioningService:
    def __init__(self, client, settings: Settings):
        self.client = client
        self.s = settings
        self._lock = threading.Lock()

    # ---- 开通 / 换线 (幂等) ----
    def provision(self, spec: LineSpec) -> ProvisionResult:
        sock = parse_socks(spec.line)            # 非法线路串先抛, 不触网
        out_tag = f"out-{spec.name}"

        with self._lock:                         # core config 读-改-写串行化
            cfg = self.client.get_core_config()
            cfg.setdefault("outbounds", [])
            cfg.setdefault("routing", {}).setdefault("rules", [])

            guard.ensure_blackhole_outbound(cfg["outbounds"])
            # upsert 本客户 outbound (先删同名再加 -> 换线路)
            cfg["outbounds"] = [o for o in cfg["outbounds"] if o.get("tag") != out_tag]
            cfg["outbounds"].append(make_outbound(out_tag, sock))

            rules = block_then_customer(cfg["routing"]["rules"], spec.name, out_tag, self.s)
            cfg["routing"]["rules"] = rules

            self.client.put_core_config(cfg)     # 失败即抛, 不建用户 (无半成品)

        user = self.client.upsert_user(self._user_body(spec))
        return ProvisionResult(
            name=spec.name,
            sub_url=self._abs_sub(user.get("subscription_url", "")),
            exit=sock.label,
            out_tag=out_tag,
            expire_days=None if spec.days == 0 else spec.days,
        )

    # ---- 删除客户 ----
    def remove(self, name: str) -> None:
        out_tag = f"out-{name}"
        with self._lock:
            cfg = self.client.get_core_config()
            cfg["outbounds"] = [o for o in cfg.get("outbounds", []) if o.get("tag") != out_tag]
            rules = cfg.get("routing", {}).get("rules", [])
            cfg.setdefault("routing", {})["rules"] = [
                r for r in rules if r.get("outboundTag") != out_tag
            ]
            self.client.put_core_config(cfg)
        self.client.delete_user(name)

    # ---- 吊销并重置订阅 (SEC-6) ----
    def rotate_sub(self, name: str) -> str:
        user = self.client.revoke_sub(name)
        return self._abs_sub(user.get("subscription_url", ""))

    # ---- 总览聚合 ----
    def list_customers(self) -> list[CustomerView]:
        users = self.client.list_users()
        exits = self._exit_map(self.client.get_core_config())
        return [self._to_view(u, exits) for u in users]

    # ---- 内部 ----
    def _user_body(self, spec: LineSpec) -> dict:
        proto = self.s.shared_inbound_protocol
        expire = 0 if spec.days == 0 else int(time.time()) + spec.days * 86400
        return {
            "username": spec.name,
            "proxies": {proto: {}},
            "inbounds": {proto: [self.s.shared_inbound_tag]},
            "expire": expire,
            "data_limit": int(spec.gb * _GB),
            "data_limit_reset_strategy": "no_reset",
        }

    def _abs_sub(self, sub: str) -> str:
        if sub.startswith("/"):
            return self.s.marzban_url.rstrip("/") + sub
        return sub

    @staticmethod
    def _exit_map(cfg: dict) -> dict[str, str]:
        out: dict[str, str] = {}
        for o in cfg.get("outbounds", []):
            tag = o.get("tag", "")
            if tag.startswith("out-"):
                srv = (o.get("settings", {}).get("servers") or [{}])[0]
                out[tag] = f"{srv.get('address', '?')}:{srv.get('port', '?')}"
        return out

    @staticmethod
    def _to_view(u: dict, exits: dict[str, str]) -> CustomerView:
        name = u.get("username", "?")
        status_map = {"active": "ok", "on_hold": "warn"}
        status = status_map.get(u.get("status", ""), "bad")
        limit = u.get("data_limit") or 0
        return CustomerView(
            name=name,
            exit=exits.get(f"out-{name}", "—"),
            status=status,
            used_gb=round((u.get("used_traffic") or 0) / _GB, 2),
            limit_gb=round(limit / _GB, 2) if limit else None,
            expire=_fmt_expire(u.get("expire")),
        )


def block_then_customer(rules: list[dict], name: str, out_tag: str, s: Settings) -> list[dict]:
    """重建护栏并置顶, 客户分流规则插其后。"""
    g = guard.block_rules(s.local_ip, s.block_smtp, s.block_bittorrent)
    customer_rule = {"type": "field", "user": [name], "outboundTag": out_tag}
    return guard.reorder_rules(rules, customer_rule, out_tag, g)


def _fmt_expire(ts) -> str:
    if not ts:
        return "不限"
    days = int((ts - time.time()) // 86400)
    return f"{days} 天" if days >= 0 else "已过期"
