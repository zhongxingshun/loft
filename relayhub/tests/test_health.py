import copy

from app.config import Settings
from app.health import HealthChecker
from app.models import HealthResult, LineSpec, SocksEndpoint
from app.provisioning import ProvisioningService


class FakeMarzban:
    def __init__(self, cfg=None):
        self.cfg = cfg or {"outbounds": [], "routing": {"rules": []}}
        self.users: dict[str, dict] = {}

    def get_core_config(self):
        return copy.deepcopy(self.cfg)

    def put_core_config(self, cfg):
        self.cfg = copy.deepcopy(cfg)

    def upsert_user(self, body):
        self.users[body["username"]] = body
        return {"username": body["username"], "subscription_url": "/sub/x"}

    def restart_core(self):
        pass


def fake_probe(ep: SocksEndpoint) -> HealthResult:
    if ep.address.startswith("9."):                 # 约定 9.x 为坏线路
        return HealthResult(ok=False, error="timeout")
    return HealthResult(ok=True, latency_ms=42, exit_ip="203.0.113.7")


def test_check_many_maps_name_and_exit():
    chk = HealthChecker(probe=fake_probe)
    items = [
        ("zhang", SocksEndpoint(address="1.2.3.4", port=8080)),
        ("bad", SocksEndpoint(address="9.9.9.9", port=1080)),
    ]
    res = chk.check_many(items)
    assert res[0].name == "zhang" and res[0].ok and res[0].exit == "1.2.3.4:8080"
    assert res[0].latency_ms == 42 and res[0].exit_ip == "203.0.113.7"
    assert res[1].name == "bad" and not res[1].ok and res[1].error == "timeout"


def test_check_many_empty():
    assert HealthChecker(probe=fake_probe).check_many([]) == []


def test_line_endpoints_extraction():
    s = Settings(_env_file=None, marzban_url="https://panel:8000", local_ip="9.9.9.9")
    svc = ProvisioningService(FakeMarzban(), s)
    svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080:u:p"))
    svc.provision(LineSpec(name="li", line="5.6.7.8:1080"))

    eps = dict(svc.line_endpoints())
    assert set(eps) == {"zhang", "li"}
    assert eps["zhang"].address == "1.2.3.4"
    assert eps["zhang"].user == "u" and eps["zhang"].password == "p"
    assert eps["li"].user is None              # 无鉴权线路
