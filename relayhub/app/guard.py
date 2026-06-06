"""出站安全护栏 (技术文档 B4.3 / SEC-5)。

核心不变量: 每次写 core 配置后, 路由表首段恒为 block 护栏规则,
任何客户分流规则都排在其后, 无法旁路。reorder_rules 为纯函数, 由单测锁定。
"""
from __future__ import annotations

BLOCK_TAG = "block"


def block_rules(local_ip: str = "", block_smtp: bool = True,
                block_bittorrent: bool = False) -> list[dict]:
    """生成出站拦截规则。

    - 私网/保留地址 geoip:private (含云元数据 169.254.169.254)
    - 本机公网 IP (防客户回打面板/SSH)
    - 出站 25 端口 (防垃圾邮件)
    - 可选 BitTorrent (降低 DMCA 投诉)
    """
    ip_list = ["geoip:private"]
    if local_ip:
        ip_list.append(f"{local_ip}/32")
    rules: list[dict] = [{"type": "field", "outboundTag": BLOCK_TAG, "ip": ip_list}]
    if block_smtp:
        rules.append({"type": "field", "outboundTag": BLOCK_TAG, "port": "25"})
    if block_bittorrent:
        rules.append({"type": "field", "outboundTag": BLOCK_TAG, "protocol": ["bittorrent"]})
    return rules


def ensure_blackhole_outbound(outbounds: list[dict]) -> None:
    """确保存在 tag=block 的 blackhole 出站, 作为护栏的丢弃目标。原地修改。"""
    if not any(o.get("tag") == BLOCK_TAG for o in outbounds):
        outbounds.append({"tag": BLOCK_TAG, "protocol": "blackhole", "settings": {}})


def reorder_rules(rules: list[dict], customer_rule: dict, out_tag: str,
                  guard: list[dict]) -> list[dict]:
    """重排路由表, 返回新列表 (不修改入参):

        [guard 护栏(置顶)] + [本客户分流] + [其余非block非本客户规则]

    丢弃旧的 block 规则 (由本函数统一重建) 与本客户旧规则 (幂等), 其余按原序保留。
    """
    others = [
        r for r in rules
        if r.get("outboundTag") not in (BLOCK_TAG, out_tag)
    ]
    return list(guard) + [customer_rule] + others
