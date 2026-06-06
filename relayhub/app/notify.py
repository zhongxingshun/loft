"""告警通知器 (P5)。Telegram Bot API。

未配置 token/chat_id 时 enabled=False, send() 静默跳过。client 可注入便于测试。
"""
from __future__ import annotations

import httpx


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None):
        self.token = token
        self.chat_id = chat_id
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        client = self._client or httpx.Client(timeout=10.0)
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            r = client.post(url, json={"chat_id": self.chat_id, "text": text})
            return r.status_code == 200
        except httpx.HTTPError:
            return False
