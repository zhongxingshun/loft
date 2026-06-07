#!/usr/bin/env python3
"""CLI 薄封装 (技术文档 B6)。复用 ProvisioningService, 与 Web 行为一致。

用法:
    python -m scripts.add_line <客户名> <decode线路串> [--days 30] [--gb 0]
    python -m scripts.add_line zhang 1.2.3.4:8080:user:pass --days 30

配置经环境变量 / .env 注入 (RELAYHUB_ 前缀), 见 app/config.py。
"""
from __future__ import annotations

import argparse
import sys

from app.config import load_settings
from app.marzban import MarzbanClient, MarzbanError
from app.models import LineSpec
from app.provisioning import ProvisioningService


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RelayHub 中转一键开通")
    ap.add_argument("name", help="客户名 (= Marzban 用户名)")
    ap.add_argument("line", help="decode SOCKS5 线路串 ip:port[:user:pass]")
    ap.add_argument("--days", type=int, default=30, help="有效天数, 0=不限")
    ap.add_argument("--gb", type=float, default=0, help="流量上限GB, 0=不限")
    args = ap.parse_args(argv)

    settings = load_settings()
    service = ProvisioningService(MarzbanClient(settings), settings)

    try:
        spec = LineSpec(name=args.name, line=args.line, days=args.days, gb=args.gb)
        result = service.provision(spec)
    except (ValueError, MarzbanError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    print(f"[OK] 安全护栏已置顶 | {result.out_tag} -> {result.exit}")
    print(f"[OK] 用户 {result.name} 已开通 "
          f"(有效期: {'不限' if result.expire_days is None else str(result.expire_days)+'天'})")
    print(f"[OK] 路由匹配键: {', '.join(result.match_keys)}")
    print("[OK] 已触发 core 重启注入新用户")
    print(f"\n订阅链接 (clash/v2ray 通用):\n{result.sub_url}\n")
    print("提示: 客户连上产生流量后, 跑 `python -m scripts.verify_routing` 核验分流是否命中。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
