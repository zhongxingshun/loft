from app.alerts import AlertService, evaluate
from app.config import Settings
from app.models import CustomerView, HealthResult


def cv(name, status="ok", used=0.0, limit=None, expire="30 天"):
    return CustomerView(name=name, exit="1.2.3.4:8080", status=status,
                        used_gb=used, limit_gb=limit, expire=expire)


def test_expiring_soon():
    a = evaluate([cv("zhang", expire="2 天")], expire_days=3)
    assert len(a) == 1 and a[0].kind == "expiring" and a[0].severity == "warn"


def test_not_expiring_when_far():
    assert evaluate([cv("zhang", expire="10 天")], expire_days=3) == []


def test_unlimited_expire_no_alert():
    assert evaluate([cv("zhang", expire="不限")]) == []


def test_traffic_threshold():
    a = evaluate([cv("zhang", used=92, limit=100)], traffic_pct=90)
    assert len(a) == 1 and a[0].kind == "traffic"
    # 未达阈值不报
    assert evaluate([cv("zhang", used=80, limit=100)], traffic_pct=90) == []


def test_unlimited_traffic_no_alert():
    assert evaluate([cv("zhang", used=9999, limit=None)]) == []


def test_expired_status():
    a = evaluate([cv("zhang", status="bad")])
    assert len(a) == 1 and a[0].kind == "expired" and a[0].severity == "bad"


def test_offline_from_health():
    health = [HealthResult(name="zhang", ok=False, error="timeout")]
    a = evaluate([cv("zhang")], health=health)
    assert any(x.kind == "offline" for x in a)


def test_multiple_alerts_one_customer():
    a = evaluate([cv("zhang", used=95, limit=100, expire="1 天")], expire_days=3, traffic_pct=90)
    kinds = {x.kind for x in a}
    assert "expiring" in kinds and "traffic" in kinds


# ---- AlertService 去重 ----

class FakeProv:
    def __init__(self, customers):
        self._c = customers
    def list_customers(self):
        return self._c
    def line_endpoints(self):
        return []


class FakeNotifier:
    def __init__(self):
        self.sent = []
        self.enabled = True
    def send(self, text):
        self.sent.append(text)
        return True


def _settings():
    return Settings(_env_file=None, alert_expire_days=3, alert_traffic_pct=90)


def test_run_once_dedupes():
    prov = FakeProv([cv("zhang", expire="2 天")])
    notifier = FakeNotifier()
    svc = AlertService(prov, _settings(), notifier)

    first = svc.run_once()
    assert len(first) == 1 and len(notifier.sent) == 1     # 首次推送
    second = svc.run_once()
    assert second == [] and len(notifier.sent) == 1        # 同条不重复推送


def test_run_once_realerts_after_resolved():
    prov = FakeProv([cv("zhang", expire="2 天")])
    notifier = FakeNotifier()
    svc = AlertService(prov, _settings(), notifier)
    svc.run_once()                                         # 推送一次

    prov._c = [cv("zhang", expire="20 天")]                # 条件解除
    assert svc.run_once() == []

    prov._c = [cv("zhang", expire="1 天")]                 # 再次临期
    again = svc.run_once()
    assert len(again) == 1 and len(notifier.sent) == 2     # 解除后可再次告警
