"""告警评估与推送 (P5)。

evaluate(): 纯函数, 把客户/探活状态映射为告警事件 (便于单测)。
AlertService: 周期性自检, 去重后经 notifier 推送 (在内存中记已发, 避免重复刷屏)。
"""
from __future__ import annotations

from .config import Settings
from .models import Alert, CustomerView, HealthResult


def _days(expire: str) -> int | None:
    """从 CustomerView.expire ('23 天' / '不限' / '已过期') 取剩余天数。"""
    s = expire.strip()
    if s.endswith("天"):
        try:
            return int(s[:-1].strip())
        except ValueError:
            return None
    return None


def evaluate(customers: list[CustomerView], expire_days: int = 3,
             traffic_pct: int = 90,
             health: list[HealthResult] | None = None) -> list[Alert]:
    alerts: list[Alert] = []
    offline = {h.name for h in (health or []) if not h.ok and h.name}

    for c in customers:
        # 已到期 / 超流量 (Marzban 状态判定)
        if c.status == "bad":
            alerts.append(Alert(name=c.name, kind="expired", severity="bad",
                                message=f"{c.name} 已到期或超流量, 已停服"))
        else:
            d = _days(c.expire)
            if d is not None and 0 <= d <= expire_days:
                alerts.append(Alert(name=c.name, kind="expiring", severity="warn",
                                    message=f"{c.name} 将在 {d} 天后到期"))
            if c.limit_gb and c.limit_gb > 0:
                pct = c.used_gb / c.limit_gb * 100
                if pct >= traffic_pct:
                    alerts.append(Alert(name=c.name, kind="traffic", severity="warn",
                                        message=f"{c.name} 流量已用 {pct:.0f}% "
                                                f"({c.used_gb}/{c.limit_gb}GB)"))
        # decode 线路探活失败
        if c.name in offline:
            alerts.append(Alert(name=c.name, kind="offline", severity="bad",
                                message=f"{c.name} 的 decode 线路探活失败, 可能已掉线"))
    return alerts


class AlertService:
    def __init__(self, provisioning, settings: Settings, notifier, checker=None):
        self.prov = provisioning
        self.s = settings
        self.notifier = notifier
        self.checker = checker
        self._sent: set[tuple[str, str]] = set()    # (name, kind) 已推送, 去重

    def current(self) -> list[Alert]:
        customers = self.prov.list_customers()
        health = None
        if self.s.alert_check_health and self.checker is not None:
            health = self.checker.check_many(self.prov.line_endpoints())
        return evaluate(customers, self.s.alert_expire_days,
                        self.s.alert_traffic_pct, health)

    def run_once(self) -> list[Alert]:
        """评估 -> 仅推送新出现的告警 -> 返回本次新推送列表。"""
        alerts = self.current()
        active = {(a.name, a.kind) for a in alerts}
        self._sent &= active                         # 条件已解除的, 清出以便日后再报
        new = [a for a in alerts if (a.name, a.kind) not in self._sent]
        for a in new:
            self.notifier.send(f"[RelayHub] ⚠️ {a.message}")
            self._sent.add((a.name, a.kind))
        return new
