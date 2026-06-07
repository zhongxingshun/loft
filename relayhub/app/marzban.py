"""Marzban REST API 客户端 (技术文档 B4.4)。

仅做 HTTP + 鉴权, 不含业务编排。token 缓存, 401 时清空重取。
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class MarzbanError(RuntimeError):
    """Marzban API 调用失败 (上层映射为 HTTP 502)。"""


class MarzbanClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.s = settings
        self._client = client or httpx.Client(
            base_url=settings.marzban_url.rstrip("/"),
            verify=settings.verify_tls,
            timeout=30.0,
        )
        self._token_cache: str | None = None

    # ---- 鉴权 ----
    def _token(self) -> str:
        if self._token_cache:
            return self._token_cache
        try:
            r = self._client.post(
                "/api/admin/token",
                data={"username": self.s.admin_user, "password": self.s.admin_pass},
            )
            r.raise_for_status()
            self._token_cache = r.json()["access_token"]
        except (httpx.HTTPError, KeyError) as e:
            raise MarzbanError(f"鉴权失败: {e}") from e
        return self._token_cache

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._token()}"
        try:
            r = self._client.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as e:
            raise MarzbanError(f"{method} {path} 网络错误: {e}") from e
        if r.status_code == 401:                 # token 失效, 清缓存重试一次
            self._token_cache = None
            headers["Authorization"] = f"Bearer {self._token()}"
            r = self._client.request(method, path, headers=headers, **kw)
        return r

    @staticmethod
    def _ok(r: httpx.Response) -> Any:
        if r.status_code >= 400:
            raise MarzbanError(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else None

    # ---- core config ----
    def get_core_config(self) -> dict:
        return self._ok(self._req("GET", "/api/core/config"))

    def put_core_config(self, cfg: dict) -> None:
        self._ok(self._req("PUT", "/api/core/config", json=cfg))

    def restart_core(self) -> None:
        """重启 Xray 核心 (全量重生成配置, 注入新增/移除用户)。轻量, 不重启容器。"""
        self._ok(self._req("POST", "/api/core/restart"))

    # ---- user ----
    def upsert_user(self, body: dict) -> dict:
        r = self._req("POST", "/api/user", json=body)
        if r.status_code == 409:                 # 已存在 -> 改 PUT 更新
            r = self._req("PUT", f"/api/user/{body['username']}", json=body)
        return self._ok(r)

    def list_users(self) -> list[dict]:
        data = self._ok(self._req("GET", "/api/users"))
        return data.get("users", data) if isinstance(data, dict) else data

    def get_user(self, name: str) -> dict:
        return self._ok(self._req("GET", f"/api/user/{name}"))

    def delete_user(self, name: str) -> None:
        self._ok(self._req("DELETE", f"/api/user/{name}"))

    def revoke_sub(self, name: str) -> dict:
        return self._ok(self._req("POST", f"/api/user/{name}/revoke_sub"))
