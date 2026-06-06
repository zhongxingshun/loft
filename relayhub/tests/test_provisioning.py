import copy

import pytest

from app.config import Settings
from app.guard import block_rules
from app.models import LineSpec
from app.provisioning import ProvisioningService


class FakeMarzban:
    """内存版 Marzban, 用于无网络集成测试。"""

    def __init__(self, cfg=None):
        self.cfg = cfg or {"outbounds": [], "routing": {"rules": []}}
        self.users: dict[str, dict] = {}
        self.deleted: list[str] = []

    def get_core_config(self):
        return copy.deepcopy(self.cfg)

    def put_core_config(self, cfg):
        self.cfg = copy.deepcopy(cfg)

    def upsert_user(self, body):
        self.users[body["username"]] = body
        return {"username": body["username"],
                "subscription_url": f"/sub/{body['username']}TOKEN"}

    def list_users(self):
        return [{"username": n, "status": "active", "used_traffic": 0,
                 "data_limit": 0, "expire": 0} for n in self.users]

    def delete_user(self, name):
        self.users.pop(name, None)
        self.deleted.append(name)

    def revoke_sub(self, name):
        return {"username": name, "subscription_url": f"/sub/{name}NEWTOKEN"}


@pytest.fixture
def settings():
    return Settings(_env_file=None, marzban_url="https://panel:8000", local_ip="9.9.9.9")


@pytest.fixture
def svc(settings):
    return ProvisioningService(FakeMarzban(), settings)


def _rules(svc):
    return svc.client.cfg["routing"]["rules"]


def test_provision_returns_result(svc, settings):
    r = svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080:u:p", days=30))
    assert r.name == "zhang"
    assert r.out_tag == "out-zhang"
    assert r.exit == "1.2.3.4:8080"
    assert r.sub_url == "https://panel:8000/sub/zhangTOKEN"
    assert r.expire_days == 30


def test_provision_writes_guard_on_top(svc, settings):
    svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080"))
    guard = block_rules(settings.local_ip, settings.block_smtp, settings.block_bittorrent)
    rules = _rules(svc)
    assert rules[: len(guard)] == guard                     # 护栏置顶
    assert rules[len(guard)]["outboundTag"] == "out-zhang"  # 客户规则紧随其后
    # blackhole 出站已就位
    assert any(o.get("tag") == "block" for o in svc.client.cfg["outbounds"])


def test_security_regression_guard_stays_on_top_with_preexisting_rules(settings):
    """关键安全回归: 即便已有客户规则在最前, provision 后护栏仍必须置顶 (SEC-5)。"""
    seeded = {
        "outbounds": [{"tag": "out-old", "protocol": "socks", "settings": {"servers": []}}],
        "routing": {"rules": [
            {"type": "field", "user": ["old"], "outboundTag": "out-old"},  # 抢在最前
        ]},
    }
    svc = ProvisioningService(FakeMarzban(seeded), settings)
    svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080"))

    guard = block_rules(settings.local_ip, settings.block_smtp, settings.block_bittorrent)
    rules = _rules(svc)
    assert rules[: len(guard)] == guard                     # 护栏被顶到最前
    assert any(r.get("outboundTag") == "out-old" for r in rules)  # 老客户保留


def test_provision_idempotent_rotate_line(svc):
    svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080"))
    r2 = svc.provision(LineSpec(name="zhang", line="5.6.7.8:9090"))   # 换线路
    outs = [o for o in svc.client.cfg["outbounds"] if o.get("tag") == "out-zhang"]
    assert len(outs) == 1                                   # 不重复
    assert outs[0]["settings"]["servers"][0]["address"] == "5.6.7.8"
    assert r2.exit == "5.6.7.8:9090"
    # 客户分流规则也不重复
    assert sum(1 for r in _rules(svc) if r.get("outboundTag") == "out-zhang") == 1
    assert len(svc.client.users) == 1


def test_remove(svc):
    svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080"))
    svc.remove("zhang")
    assert not any(o.get("tag") == "out-zhang" for o in svc.client.cfg["outbounds"])
    assert not any(r.get("outboundTag") == "out-zhang" for r in _rules(svc))
    assert "zhang" in svc.client.deleted


def test_rotate_sub(svc):
    svc.provision(LineSpec(name="zhang", line="1.2.3.4:8080"))
    new = svc.rotate_sub("zhang")
    assert new == "https://panel:8000/sub/zhangNEWTOKEN"


def test_bad_line_does_not_touch_config(svc):
    with pytest.raises(ValueError):
        svc.provision(LineSpec(name="zhang", line="not-a-line"))
    assert _rules(svc) == []                                # 配置未被改动
    assert svc.client.users == {}
