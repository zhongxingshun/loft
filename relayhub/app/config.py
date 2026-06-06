"""配置与密钥 (技术文档 B4.1)。

所有敏感项经环境变量 / .env 注入, 不写死在代码里 (SEC-7)。
环境变量前缀 RELAYHUB_, 例如 RELAYHUB_ADMIN_PASS=xxx。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- Marzban 面板 ----
    marzban_url: str = "https://your-vps-domain:8000"
    admin_user: str = "admin"
    admin_pass: str = "change-me"

    # ---- 共享 inbound ----
    shared_inbound_tag: str = "VLESS_WS_INBOUND"
    shared_inbound_protocol: str = "vless"      # vless / vmess / trojan
    verify_tls: bool = True                     # 自签证书改 False

    # ---- 出站安全护栏 (SEC-5) ----
    local_ip: str = ""                          # 本机公网 IP, 防客户回打面板/SSH
    block_smtp: bool = True                     # 封出站 25 端口
    block_bittorrent: bool = False              # 封 BT, 降低 DMCA 投诉

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RELAYHUB_",
        extra="ignore",
    )


def load_settings() -> Settings:
    return Settings()
