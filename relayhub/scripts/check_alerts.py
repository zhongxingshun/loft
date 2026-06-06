#!/usr/bin/env python3
"""告警检查 CLI (P5)。

默认仅**预览**当前告警; 加 --send 真正推送一次 (用于测试 Telegram 配置是否通)。

用法:
    docker compose exec relayhub python -m scripts.check_alerts
    docker compose exec relayhub python -m scripts.check_alerts --send

持续告警建议用后台定时: 在 .env 设 RELAYHUB_ALERT_INTERVAL_MIN=10 (并配好 Telegram),
RelayHub 启动后会每 10 分钟自检并推送 (内存去重, 不刷屏)。
"""
from __future__ import annotations

import argparse

from app.alerts import AlertService
from app.config import load_settings
from app.health import HealthChecker
from app.marzban import MarzbanClient, MarzbanError
from app.notify import TelegramNotifier
from app.provisioning import ProvisioningService


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RelayHub 告警检查")
    ap.add_argument("--send", action="store_true", help="真正推送一次 (默认仅预览)")
    args = ap.parse_args(argv)

    s = load_settings()
    prov = ProvisioningService(MarzbanClient(s), s)
    notifier = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    svc = AlertService(prov, s, notifier, HealthChecker())

    try:
        alerts = svc.current()
    except MarzbanError as e:
        print(f"[ERROR] {e}")
        return 1

    if not alerts:
        print("✅ 当前无告警")
        return 0

    print(f"当前 {len(alerts)} 条告警:")
    for a in alerts:
        flag = "🔴" if a.severity == "bad" else "🟡"
        print(f"  {flag} [{a.kind}] {a.message}")

    if args.send:
        sent = svc.run_once()
        if not notifier.enabled:
            print("\n⚠️ Telegram 未配置 (telegram_bot_token / telegram_chat_id), 未实际推送")
        else:
            print(f"\n已推送 {len(sent)} 条 (其余为已推送过的, 去重跳过)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
