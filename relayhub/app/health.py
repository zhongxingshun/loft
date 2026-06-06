"""线路健康检查 (P5)。

对每条 decode SOCKS5 出口做真实探活: 经该代理访问探测目标, 测延迟与出口 IP。
探测函数可注入 (probe), 便于单测无网络运行。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import httpx

from .models import HealthResult, SocksEndpoint

# 默认探测目标: 返回 JSON {"ip": "..."}, 体积小、稳定
DEFAULT_TARGET = "https://api.ipify.org?format=json"

Probe = Callable[[SocksEndpoint], HealthResult]


class HealthChecker:
    def __init__(self, timeout: float = 8.0, target: str = DEFAULT_TARGET,
                 probe: Probe | None = None, max_workers: int = 10):
        self.timeout = timeout
        self.target = target
        self.max_workers = max_workers
        self._probe = probe or self._http_probe

    def check(self, ep: SocksEndpoint) -> HealthResult:
        return self._probe(ep)

    def check_many(self, items: list[tuple[str, SocksEndpoint]]) -> list[HealthResult]:
        """并发探测 [(name, endpoint), ...], 返回与输入同序的结果 (带 name/exit)。"""
        if not items:
            return []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(items))) as ex:
            raw = list(ex.map(lambda it: self._probe(it[1]), items))
        out: list[HealthResult] = []
        for (name, ep), res in zip(items, raw):
            out.append(res.model_copy(update={"name": name, "exit": ep.label}))
        return out

    # ---- 真实 HTTP 探测 (经 socks5 出站) ----
    def _http_probe(self, ep: SocksEndpoint) -> HealthResult:
        auth = f"{ep.user}:{ep.password}@" if ep.user else ""
        proxy = f"socks5://{auth}{ep.address}:{ep.port}"
        t0 = time.monotonic()
        try:
            with httpx.Client(proxy=proxy, timeout=self.timeout) as c:
                r = c.get(self.target)
                r.raise_for_status()
                ip = None
                if "json" in r.headers.get("content-type", ""):
                    ip = r.json().get("ip")
            ms = int((time.monotonic() - t0) * 1000)
            return HealthResult(ok=True, latency_ms=ms, exit_ip=ip)
        except Exception as e:  # noqa: BLE001 — 探活失败均视为线路不可用
            return HealthResult(ok=False, error=str(e)[:120] or e.__class__.__name__)
