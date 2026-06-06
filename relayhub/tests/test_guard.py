from app.guard import (
    BLOCK_TAG,
    block_rules,
    ensure_blackhole_outbound,
    reorder_rules,
)


def test_block_rules_default():
    rules = block_rules()
    assert rules[0]["ip"] == ["geoip:private"]
    # 默认封 SMTP
    assert any(r.get("port") == "25" for r in rules)
    # 默认不封 BT
    assert not any("protocol" in r for r in rules)


def test_block_rules_with_local_ip_and_bt():
    rules = block_rules(local_ip="9.9.9.9", block_smtp=False, block_bittorrent=True)
    assert "9.9.9.9/32" in rules[0]["ip"]
    assert not any(r.get("port") == "25" for r in rules)
    assert any(r.get("protocol") == ["bittorrent"] for r in rules)


def test_ensure_blackhole_idempotent():
    outs: list[dict] = []
    ensure_blackhole_outbound(outs)
    ensure_blackhole_outbound(outs)
    blocks = [o for o in outs if o.get("tag") == BLOCK_TAG]
    assert len(blocks) == 1
    assert blocks[0]["protocol"] == "blackhole"


def test_reorder_puts_guard_on_top():
    existing = [
        {"type": "field", "user": ["other"], "outboundTag": "out-other"},
        {"type": "field", "outboundTag": "block", "ip": ["stale"]},  # 旧护栏应被丢弃
    ]
    guard = block_rules(local_ip="9.9.9.9")
    customer = {"type": "field", "user": ["zhang"], "outboundTag": "out-zhang"}
    result = reorder_rules(existing, customer, "out-zhang", guard)

    # 护栏恒在最前
    assert result[: len(guard)] == guard
    # 紧接着是本客户
    assert result[len(guard)] == customer
    # 旧的 stale 护栏被清掉, 只剩重建的护栏
    assert sum(1 for r in result if r.get("outboundTag") == "block") == len(guard)
    # 其它客户保留
    assert any(r.get("outboundTag") == "out-other" for r in result)


def test_reorder_idempotent_no_dup_customer():
    guard = block_rules()
    customer = {"type": "field", "user": ["zhang"], "outboundTag": "out-zhang"}
    r1 = reorder_rules([], customer, "out-zhang", guard)
    r2 = reorder_rules(r1, customer, "out-zhang", guard)
    # 重跑不重复本客户规则
    assert sum(1 for r in r2 if r.get("outboundTag") == "out-zhang") == 1
    # 护栏依旧置顶且不翻倍
    assert r2[: len(guard)] == guard
    assert sum(1 for r in r2 if r.get("outboundTag") == "block") == len(guard)
