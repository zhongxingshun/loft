#!/usr/bin/env python3
"""逐跳追踪某客户访问 claude.ai 的完整链路并打印。

用法 (在服务器上, 容器外宿主机):
    set -a; source /opt/relayhub-stack/.env; set +a
    python3 trace_chain.py [username] [target]

不传 username 时, 自动找出口 IP = TARGET_EXIT_IP 的那个客户。
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.request

MARZBAN = "https://127.0.0.1:8000"
TARGET = sys.argv[2] if len(sys.argv) > 2 else "claude.ai"
WANT_USER = sys.argv[1] if len(sys.argv) > 1 else None

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def api(path, data=None, token=None):
    url = MARZBAN + path
    headers = {}
    body = None
    if data is not None:
        body = "&".join(f"{k}={v}" for k, v in data.items()).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, context=_ctx, timeout=20) as r:
        return json.loads(r.read())


def curl_proxy(proxy, url, want="ip"):
    """经 socks5 发请求, 返回 (出口IP 或 HTTP码, 耗时)。"""
    if want == "ip":
        cmd = ["curl", "-s", "--max-time", "25", "-x", proxy,
               "-w", "\n%{time_total}", "https://api.ipify.org"]
    else:
        cmd = ["curl", "-s", "--max-time", "25", "-x", proxy, "-o", "/dev/null",
               "-w", "%{http_code}\n%{time_total}", url]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().split("\n")
    return (out[0] if out else "?", out[-1] if len(out) > 1 else "?")


def line(n, title):
    print(f"\n[{n}] {title}")


def main():
    admin_u = os.environ.get("MARZBAN_ADMIN_USER", "admin")
    admin_p = os.environ.get("MARZBAN_ADMIN_PASS", "")
    token = api("/api/admin/token",
                {"username": admin_u, "password": admin_p})["access_token"]
    cfg = api("/api/core/config", token=token)
    outbounds = {o.get("tag"): o for o in cfg.get("outbounds", [])}
    rules = cfg.get("routing", {}).get("rules", [])

    # 选定客户
    users = api("/api/users?limit=200", token=token).get("users", [])
    target_user = None
    if WANT_USER:
        target_user = WANT_USER
    else:
        # 自动找: 遍历每个 out-<user> 测出口, 命中 9.142.76.61
        want_ip = "9.142.76.61"
        for u in users:
            tag = f"out-{u['username']}"
            if tag in outbounds:
                s = outbounds[tag]["settings"]["servers"][0]
                usr = (s.get("users") or [{}])[0]
                proxy = f"socks5h://{usr.get('user')}:{usr.get('pass')}@{s['address']}:{s['port']}"
                ip, _ = curl_proxy(proxy, None, "ip")
                if ip == want_ip:
                    target_user = u["username"]
                    break
    if not target_user:
        print("找不到客户"); return

    user = api(f"/api/user/{target_user}", token=token)
    proto = list(user.get("proxies", {}).keys())
    note = user.get("note")

    print("=" * 60)
    print(f"  追踪客户: {target_user}   访问目标: https://{TARGET}")
    print("=" * 60)

    line(1, "本地客户端 (你的浏览器/Claude)")
    print("    → 本地 Clash 接管 (TUN / 系统代理)")

    line(2, "本地 Clash 规则匹配")
    print(f"    域名 {TARGET} → 命中规则 → 🤖 AI 专线 (走本节点, 不走机场)")

    line(3, "入口: 你的中转节点 (VLESS+Reality)")
    server_ip = "23.252.105.218"
    code = subprocess.run(["bash", "-c",
        f"timeout 5 bash -c 'echo>/dev/tcp/{server_ip}/443' && echo open || echo closed"],
        capture_output=True, text=True).stdout.strip()
    print(f"    {server_ip}:443  端口={code}  (伪装 SNI=www.microsoft.com)")

    line(4, "服务器 Xray 路由 (按用户分流)")
    tag = f"out-{target_user}"
    hit = [r for r in rules if any(target_user in str(x) for x in (r.get("user") or []))]
    print(f"    入站用户标识={proto}  email前缀={{id}}.{target_user}")
    print(f"    匹配路由 → 出站 {hit[0].get('outboundTag') if hit else '(未命中!)'}")

    line(5, "出站: 你的专属 ISP 住宅 SOCKS5")
    s = outbounds[tag]["settings"]["servers"][0]
    usr = (s.get("users") or [{}])[0]
    proxy = f"socks5h://{usr.get('user')}:{usr.get('pass')}@{s['address']}:{s['port']}"
    print(f"    {s['address']}:{s['port']}  (note 记录: {note})")

    line(6, f"出口 → 目标 https://{TARGET}")
    ip, t_ip = curl_proxy(proxy, None, "ip")
    print(f"    实测出口 IP = {ip}   (取IP耗时 {t_ip}s)")
    hc, t_t = curl_proxy(proxy, f"https://{TARGET}/", "code")
    print(f"    访问 {TARGET} → HTTP {hc}  (耗时 {t_t}s)")
    hc2, _ = curl_proxy(proxy, "https://www.anthropic.com/", "code")
    print(f"    访问 anthropic.com → HTTP {hc2}")

    print("\n" + "=" * 60)
    print(f"  结论: {target_user} 的 AI 流量经 节点{server_ip} → ISP{s['address']} 出口 {ip}")
    print("=" * 60)


if __name__ == "__main__":
    main()
