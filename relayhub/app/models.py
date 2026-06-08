"""pydantic 数据模型 (技术文档 B4.6)。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SocksEndpoint(BaseModel):
    """decode SOCKS5 线路端点。"""
    address: str
    port: int
    user: Optional[str] = None
    password: Optional[str] = None

    @property
    def label(self) -> str:
        return f"{self.address}:{self.port}"


class LineSpec(BaseModel):
    """开通入参。name 受限字符集, 既作 Marzban 用户名也作路由匹配键。"""
    name: str = Field(pattern=r"^[a-zA-Z0-9_]{2,32}$")
    line: str                       # ip:port[:user:pass]
    days: int = 30                  # 0 = 不限
    gb: float = 0                   # 0 = 不限
    exit_ip: Optional[str] = None   # 出口 IP (可选, 手填, 显示在节点名上)


class ProvisionResult(BaseModel):
    """开通结果, 回给前端 / CLI。"""
    name: str
    sub_url: str
    exit: str                       # 出口 ip:port
    out_tag: str
    expire_days: Optional[int] = None
    match_keys: list[str] = []      # 路由 user 多候选 (兼容不同 email 格式)
    exit_ip: Optional[str] = None   # 开通时探测到的 decode 出口 IP


class CustomerView(BaseModel):
    """总览表格行 (技术文档 B5: GET /api/lines)。"""
    name: str
    exit: str
    status: Literal["ok", "warn", "bad"]
    used_gb: float
    limit_gb: Optional[float] = None
    expire: str


class HealthResult(BaseModel):
    """单条 decode 线路探活结果 (P5: GET /api/health)。"""
    name: Optional[str] = None
    exit: Optional[str] = None
    ok: bool
    latency_ms: Optional[int] = None
    exit_ip: Optional[str] = None      # 经该线路出站看到的公网 IP
    error: Optional[str] = None


class Alert(BaseModel):
    """告警事件 (P5)。"""
    name: str
    kind: Literal["expiring", "traffic", "expired", "offline"]
    severity: Literal["warn", "bad"]
    message: str
