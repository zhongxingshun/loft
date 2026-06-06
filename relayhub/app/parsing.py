"""线路串解析 (技术文档 B4.2)。"""
from __future__ import annotations

from .models import SocksEndpoint


def parse_socks(line: str) -> SocksEndpoint:
    """解析 decode SOCKS5 线路串。

    支持:  ip:port            (无鉴权)
           ip:port:user:pass  (带鉴权)
    非法格式抛 ValueError, 不触网。
    """
    parts = line.strip().split(":")
    if len(parts) == 2:
        return SocksEndpoint(address=parts[0], port=_port(parts[1]))
    if len(parts) == 4:
        return SocksEndpoint(
            address=parts[0], port=_port(parts[1]), user=parts[2], password=parts[3]
        )
    raise ValueError(f"线路串格式错误: {line!r}  期望 ip:port 或 ip:port:user:pass")


def _port(s: str) -> int:
    try:
        p = int(s)
    except ValueError:
        raise ValueError(f"端口非数字: {s!r}") from None
    if not (0 < p < 65536):
        raise ValueError(f"端口越界: {p}")
    return p
