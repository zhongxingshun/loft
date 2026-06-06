from app.diagnostics import (
    classify_outbound,
    misrouted,
    parse_access_log,
    routing_report,
)

SAMPLE = """\
2026/06/06 03:04:05 from 198.51.100.7:51234 accepted tcp:www.google.com:443 [VLESS_REALITY -> out-zhang] email: zhang
2026/06/06 03:04:06 from 198.51.100.7:51235 accepted tcp:cdn.example.com:443 [VLESS_REALITY -> out-zhang] email: zhang
2026/06/06 03:04:07 from 198.51.100.7:51236 accepted tcp:10.0.0.5:25 [VLESS_REALITY -> block] email: zhang
2026/06/06 03:04:08 from 203.0.113.9:40001 accepted tcp:api.test.com:443 [VLESS_REALITY -> direct] email: 7.wang
2026/06/06 03:04:09 from 1.1.1.1:5 accepted udp:8.8.8.8:53 [api -> direct]
"""


def test_parse_basic():
    e = parse_access_log(SAMPLE)
    assert len(e) == 5
    first = e[0]
    assert first.target == "www.google.com:443"
    assert first.inbound == "VLESS_REALITY"
    assert first.outbound == "out-zhang"
    assert first.email == "zhang"
    # 无 email 的 DNS 行
    assert e[-1].email is None and e[-1].outbound == "direct"


def test_classify():
    assert classify_outbound("out-zhang") == "分流命中"
    assert classify_outbound("direct").startswith("走默认")
    assert classify_outbound("freedom").startswith("走默认")
    assert classify_outbound("block") == "护栏拦截"


def test_routing_report_aggregates():
    rows = routing_report(parse_access_log(SAMPLE))
    # zhang -> out-zhang 出现两次, 聚合为 count=2 且排在最前
    top = rows[0]
    assert top.email == "zhang" and top.outbound == "out-zhang" and top.count == 2
    # 各组合都在
    keys = {(r.email, r.outbound) for r in rows}
    assert ("zhang", "block") in keys
    assert ("7.wang", "direct") in keys


def test_misrouted_flags_real_email_going_direct():
    bad = misrouted(routing_report(parse_access_log(SAMPLE)))
    emails = {r.email for r in bad}
    # 7.wang 带真实 email 却走 direct -> 标记为疑似失效 (暴露了 id 前缀格式)
    assert "7.wang" in emails
    # DNS 那条没 email, 不应被标记
    assert "-" not in emails
