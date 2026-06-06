#!/usr/bin/env python3
"""
Marzban 中转一键开通脚本
用法:
    python3 add_line.py <客户名> <decode线路串> [--days 30] [--gb 0]

decode线路串格式(SOCKS5):  ip:port:user:pass   或   ip:port  (无鉴权)

脚本会自动:
  0) 确保存在出站安全护栏: block(blackhole) 出站 + 恒置顶的拦截规则
     (禁止客户访问私网/本机/云元数据/SMTP, 防跳板与滥用投诉, 对应设计 §6.4 / SEC-5)
  1) 向 Xray core 配置追加一个 SOCKS5 outbound (tag = out-<客户名>)
  2) 追加一条路由规则: user=<客户名> -> outbound out-<客户名> (插在 block 规则之后)
  3) 创建 Marzban 用户 <客户名>
  4) 打印该用户的订阅链接 (clash / v2ray 通用)

重复执行同一个客户名 = 更新该客户的线路(换 decode IP 时直接重跑即可)。
每次运行都会重建并置顶 block 规则, 确保安全护栏不被旁路。
"""
import sys, json, argparse, requests

# ===== 改这里 =====
MARZBAN_URL = "https://your-vps-domain:8000"   # 你的中转面板地址
ADMIN_USER  = "admin"
ADMIN_PASS  = "change-me"
# 这个客户被分配到的共享 inbound 名称(在面板里建好的那个)
SHARED_INBOUND_TAG = "VLESS_WS_INBOUND"
SHARED_INBOUND_PROTOCOL = "vless"              # vless / vmess / trojan
VERIFY_TLS = True                              # 自签证书改 False

# ----- 出站安全护栏 (SEC-5) -----
LOCAL_IP = ""              # 本机公网IP, 防客户回打面板/SSH; 留空则仅封私网网段
BLOCK_SMTP = True          # 封出站 25 端口, 防垃圾邮件投诉
BLOCK_BITTORRENT = False   # 封 BT, 降低美国机房 DMCA/abuse 投诉 (按需开启)
# ==================


def parse_socks(line: str):
    parts = line.strip().split(":")
    if len(parts) == 2:
        return {"address": parts[0], "port": int(parts[1]), "user": None, "pass": None}
    if len(parts) == 4:
        return {"address": parts[0], "port": int(parts[1]), "user": parts[2], "pass": parts[3]}
    raise ValueError(f"线路串格式错误: {line!r}  期望 ip:port 或 ip:port:user:pass")


def make_outbound(tag: str, sock: dict) -> dict:
    server = {"address": sock["address"], "port": sock["port"]}
    if sock["user"]:
        server["users"] = [{"user": sock["user"], "pass": sock["pass"]}]
    return {"tag": tag, "protocol": "socks", "settings": {"servers": [server]}}


def block_rules() -> list:
    """生成出站拦截规则 (SEC-5)。每次运行重建并置顶, 防止被分流规则旁路。"""
    ip_list = ["geoip:private"]          # 含 10/8 172.16/12 192.168/16 127/8 169.254/16(云元数据)
    if LOCAL_IP:
        ip_list.append(f"{LOCAL_IP}/32")  # 防客户回打本机面板/SSH
    rules = [{"type": "field", "outboundTag": "block", "ip": ip_list}]
    if BLOCK_SMTP:
        rules.append({"type": "field", "outboundTag": "block", "port": "25"})
    if BLOCK_BITTORRENT:
        rules.append({"type": "field", "outboundTag": "block", "protocol": ["bittorrent"]})
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="客户名(同时作为 Marzban 用户名)")
    ap.add_argument("line", help="decode SOCKS5 线路串 ip:port[:user:pass]")
    ap.add_argument("--days", type=int, default=30, help="有效天数, 0=不限")
    ap.add_argument("--gb", type=float, default=0, help="流量上限GB, 0=不限")
    args = ap.parse_args()

    name = args.name
    out_tag = f"out-{name}"
    sock = parse_socks(args.line)

    s = requests.Session()
    s.verify = VERIFY_TLS

    # 1) 登录
    tok = s.post(f"{MARZBAN_URL}/api/admin/token",
                 data={"username": ADMIN_USER, "password": ADMIN_PASS}).json()["access_token"]
    s.headers["Authorization"] = f"Bearer {tok}"

    # 2) 拉当前 core 配置, 追加 outbound + routing rule (幂等: 先删同名再加)
    cfg = s.get(f"{MARZBAN_URL}/api/core/config").json()
    cfg.setdefault("outbounds", [])
    cfg.setdefault("routing", {}).setdefault("rules", [])

    # 2a) 确保存在 block(blackhole) 出站 —— 安全护栏的丢弃目标
    if not any(o.get("tag") == "block" for o in cfg["outbounds"]):
        cfg["outbounds"].append({"tag": "block", "protocol": "blackhole", "settings": {}})

    # 2b) 该客户的 SOCKS5 出站 (幂等: 先删同名再加)
    cfg["outbounds"] = [o for o in cfg["outbounds"] if o.get("tag") != out_tag]
    cfg["outbounds"].append(make_outbound(out_tag, sock))

    # 2c) 重建路由表, 顺序: [block 护栏(置顶)] -> [本客户分流] -> [其余客户/默认规则]
    #     丢弃旧的 block 规则(由脚本统一重建)与本客户旧规则, 保留其它规则原序
    others = [r for r in cfg["routing"]["rules"]
              if r.get("outboundTag") not in ("block", out_tag)]
    customer_rule = {"type": "field", "user": [name], "outboundTag": out_tag}
    cfg["routing"]["rules"] = block_rules() + [customer_rule] + others

    r = s.put(f"{MARZBAN_URL}/api/core/config", json=cfg)
    r.raise_for_status()
    print(f"[OK] 安全护栏(block)已置顶 | outbound {out_tag} -> {sock['address']}:{sock['port']} 已写入")

    # 3) 创建/更新用户
    import time
    expire = 0 if args.days == 0 else int(time.time()) + args.days * 86400
    data_limit = int(args.gb * 1024 ** 3)
    body = {
        "username": name,
        "proxies": {SHARED_INBOUND_PROTOCOL: {}},
        "inbounds": {SHARED_INBOUND_PROTOCOL: [SHARED_INBOUND_TAG]},
        "expire": expire,
        "data_limit": data_limit,
        "data_limit_reset_strategy": "no_reset",
    }
    resp = s.post(f"{MARZBAN_URL}/api/user", json=body)
    if resp.status_code == 409:          # 已存在 -> 改用 modify
        resp = s.put(f"{MARZBAN_URL}/api/user/{name}", json=body)
    resp.raise_for_status()
    user = resp.json()

    # 4) 输出订阅
    sub = user.get("subscription_url", "")
    if sub and sub.startswith("/"):
        sub = MARZBAN_URL + sub
    print(f"[OK] 用户 {name} 已开通")
    print(f"\n订阅链接 (clash/v2ray 通用):\n{sub}\n")


if __name__ == "__main__":
    main()
