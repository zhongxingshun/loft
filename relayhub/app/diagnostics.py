"""路由核验 (P1 任务 1.6 自动化)。

从 Xray 访问日志解析每条连接的 (email -> outbound), 直接证明分流是否命中:
  - outbound = out-<客户>  => 分流命中, 流量确实走该客户的 decode 出口
  - outbound = direct/freedom => 走默认出口 (很可能 email 未匹配, 分流失效)
  - outbound = block       => 被出站护栏拦截 (私网/25, 符合预期)

无需额外客户端, 真实 email 格式也一并暴露, 便于校正多候选匹配。
"""
from __future__ import annotations

import re

from pydantic import BaseModel

# 形如:
#   from 1.2.3.4:5678 accepted tcp:www.google.com:443 [VLESS_REALITY -> out-zhang] email: zhang
LINE_RE = re.compile(
    r"accepted\s+\w+:(?P<target>\S+)\s+"
    r"\[(?P<inbound>.+?)\s*->\s*(?P<outbound>[^\]]+?)\]"
    r"(?:\s+email:\s*(?P<email>\S+))?"
)


class LogEntry(BaseModel):
    target: str
    inbound: str
    outbound: str
    email: str | None = None


class RoutingRow(BaseModel):
    email: str
    outbound: str
    count: int
    verdict: str            # 分流命中 / 走默认(未命中分流?) / 护栏拦截 / 其它


def parse_access_log(text: str) -> list[LogEntry]:
    out: list[LogEntry] = []
    for m in LINE_RE.finditer(text):
        out.append(LogEntry(
            target=m.group("target"),
            inbound=m.group("inbound").strip(),
            outbound=m.group("outbound").strip(),
            email=(m.group("email") or None),
        ))
    return out


def classify_outbound(tag: str) -> str:
    if tag.startswith("out-"):
        return "分流命中"
    if tag in ("direct", "freedom", ""):
        return "走默认(未命中分流?)"
    if tag == "block":
        return "护栏拦截"
    return "其它: " + tag


def routing_report(entries: list[LogEntry]) -> list[RoutingRow]:
    """按 (email, outbound) 聚合计数, 附判定, 按 count 降序。"""
    counts: dict[tuple[str, str], int] = {}
    for e in entries:
        key = (e.email or "-", e.outbound)
        counts[key] = counts.get(key, 0) + 1
    rows = [
        RoutingRow(email=email, outbound=ob, count=n, verdict=classify_outbound(ob))
        for (email, ob), n in counts.items()
    ]
    rows.sort(key=lambda r: r.count, reverse=True)
    return rows


def misrouted(rows: list[RoutingRow]) -> list[RoutingRow]:
    """疑似分流失效的行: 有真实 email 却走了默认出口。"""
    return [r for r in rows if r.email != "-" and r.verdict.startswith("走默认")]
