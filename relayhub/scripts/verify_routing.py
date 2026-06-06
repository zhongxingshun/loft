#!/usr/bin/env python3
"""路由核验 CLI (P1 任务 1.6)。

读取 Xray 访问日志, 报告每个客户的流量实际走了哪个出口, 判定分流是否命中。

用法 (在 VPS 上, 集成栈):
    # 方式一: 管道喂日志
    docker compose logs marzban --no-color | \
        docker compose exec -T relayhub python -m scripts.verify_routing

    # 方式二: 先落盘再读
    docker compose logs marzban --no-color > /tmp/m.log
    docker compose exec -T relayhub python -m scripts.verify_routing /tmp/m.log

前提: 客户已连上并产生过流量 (这样日志里才有记录)。
"""
from __future__ import annotations

import sys

from app.diagnostics import misrouted, parse_access_log, routing_report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = open(argv[0], encoding="utf-8", errors="ignore").read() if argv else sys.stdin.read()

    entries = parse_access_log(text)
    if not entries:
        print("未从日志中解析到访问记录。确认客户已连上并产生流量, "
              "且 Xray loglevel 至少为 info/warning。", file=sys.stderr)
        return 2

    rows = routing_report(entries)
    print(f"{'EMAIL':<28} {'OUTBOUND':<16} {'次数':>5}  判定")
    print("-" * 66)
    for r in rows:
        print(f"{r.email:<28} {r.outbound:<16} {r.count:>5}  {r.verdict}")

    bad = misrouted(rows)
    print("-" * 66)
    if bad:
        print(f"⚠️  {len(bad)} 个 email 走了默认出口, 分流可能未命中:")
        for r in bad:
            print(f"    - {r.email}  (真实 email 格式即上面这串, 据此校正 email_candidates)")
        return 1
    print("✅ 未发现明显分流失效 (所有带 email 的流量都命中 out-* 或被护栏拦截)。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
