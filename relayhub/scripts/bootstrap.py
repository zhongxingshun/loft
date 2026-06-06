#!/usr/bin/env python3
"""部署初始化 (集成栈用)。

容器启动时运行: 等待 Marzban 就绪 -> 确保出站安全护栏置顶 -> 报告现有线路数。
幂等, 可重复执行。失败不阻塞 Web 启动 (best-effort)。
"""
from __future__ import annotations

import sys
import time

from app.config import load_settings
from app.marzban import MarzbanClient, MarzbanError
from app.provisioning import ProvisioningService

RETRIES = 60
INTERVAL = 2.0


def main() -> int:
    s = load_settings()
    client = MarzbanClient(s)

    for i in range(RETRIES):
        try:
            client.get_core_config()
            break
        except MarzbanError:
            if i == 0:
                print("[bootstrap] 等待 Marzban 就绪…")
            time.sleep(INTERVAL)
    else:
        print("[bootstrap] Marzban 未在预期时间内就绪, 跳过初始化", file=sys.stderr)
        return 1

    svc = ProvisioningService(client, s)
    svc.ensure_guard()
    eps = svc.line_endpoints()
    print(f"[bootstrap] 安全护栏已就位 (私网/本机/25端口拦截); 现有线路 {len(eps)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
