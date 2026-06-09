# CLAUDE.md — 项目记忆 / 运维手册

> 给 Claude 的工作记忆。**敏感值不写这里**(密钥在 `.env` / `deploy/certs/` / `deploy/xray_config.json`,均已 gitignore)。

## 这是什么

ISP IP **中转/转售**服务:买静态住宅 ISP(decode/Decodo SOCKS5)出口,用一台中转 VPS 把客户流量链式转发到其专属住宅 IP,并生成订阅(Clash/VLESS)。每个客户一条**专属住宅出口**。

技术栈:**Marzban(面板)+ Xray(核心,VLESS-Reality)+ RelayHub(自研 FastAPI 编排)+ Caddy(订阅/面板反代)**,全部 `docker compose` 编排。

## 核心架构:分流(Split Routing)

客户端**一个订阅,两条线**:

| 流量 | 规则组 | 路径 | 出口 |
|---|---|---|---|
| **AI**(Claude/GPT/Gemini…+ ping0.cc/net.coffee 检测站) | 🤖 AI 专线 | 客户端→**中转节点**→客户专属 ISP | 住宅 IP(干净、固定) |
| **其余所有** | 🚀 大流量 | 客户端→**直连大流量机场**(url-test 选最快) | 机场 IP(共享,**不过中转服务器**) |
| 国内 / 微信腾讯 | 🎯 全球直连 | 直连 | 本地 |

设计目的:AI 走住宅防风控;重流量走机场,**省中转服务器的 2TB**。

## 生产环境

- **NY 服务器**:`23.252.105.218`,部署目录 `/opt/relayhub-stack`,SSH 私钥 `~/.ssh/id_ed25519`(密码登录密钥见历史,不入库)
- **大流量机场**:导入到 RelayHub 的第三方订阅(`HIGHVOL_SUB_URL` in `.env`),拉取时需 `User-Agent: clash.meta`
- 订阅入口:`http://23.252.105.218/sub/{token}`(经 Caddy:80 → RelayHub:8080)
- 面板:Marzban `127.0.0.1:8000`、RelayHub `127.0.0.1:8080`(公网经 Caddy:8443 + Basic Auth)
- 唯一对公网业务端口:`443`(VLESS-Reality,伪装 SNI=www.microsoft.com)

## 改配置的标准流程 ⚠️ 必读

1. 改 `deploy/clash-template.yml`(分流规则、DNS、fake-ip-filter 都在这)
2. `rsync` 到服务器 `/opt/relayhub-stack/deploy/clash-template.yml`
3. **`docker compose restart marzban`** —— 模板在**开机时读进内存**,不重启不生效
4. 客户端**刷新订阅**即可(链接不变)

### 关键事实(实测验证过)

- ✅ **重启 marzban 不会让已发订阅 token 失效**(同 token 重启后仍 200)。早期那次 token 失效是一次性密钥建立,非每次重启。放心重启。
- ✅ 订阅是**服务器实时渲染**的:同一条链接每次拉都拿最新模板。客户只需刷新,**不用换链接,账号/UUID 不变**。
- ⚠️ **出口 IP 由服务器端 SOCKS5 出站(`isp.decodo.com:端口`)决定,与客户端 clash 规则无关**。Decodo ISP 产品一个端口 = 一个固定住宅 IP(实测 12/12 稳定,**不轮换**)。
- ⚠️ 改模板**必须重启** marzban 才生效(已验证:不重启拉订阅看不到改动)。

## 路由机制(RelayHub)

- Marzban 的 xray email = `{id}.{username}`(如 `1.jeffrey10001`),API 取不到 id → 路由 user 候选枚举 `{1..routing_id_range}.{name}` 全覆盖(`routing_id_range=1000`)。
- 每客户一条出站 `out-{username}` → 其 SOCKS5;路由按 user(email)分流。
- 出站安全护栏(SEC-5)永远置顶:封私网 IP(`geoip:private`)、本机 IP、25 端口。
- 开通后必须 `POST /api/core/restart` 把新用户注入 XRAY_JSON inbound,否则新客户"完全没网络"。

## 踩坑记录

- **Clash TUN 拦截服务器 IP** → 自引用回环、SSH/面板连不上。模板首条规则 `IP-CIDR,23.252.105.218/32,🎯 全球直连,no-resolve` 解决。另 `DST-PORT,22→直连` 让所有 SSH 直连。
- **fake-ip 无白名单 → 微信发图卡、通话断、智能家居发现不了**。微信等做连通性检测/UDP打洞,拿到假 IP 会反复重试。已加 46 条 `fake-ip-filter`(微信/QQ/腾讯、STUN、苹果推送、米家、系统联网检测、NTP、手游)。
- **DB 不持久**:`SQLALCHEMY_DATABASE_URL=sqlite:////var/lib/marzban/db.sqlite3`(放进卷,否则重建容器丢用户)。
- **Marzban 无证书只绑 127.0.0.1**:挂自签证书 + `UVICORN_SSL_CA_TYPE=private`。
- **xray_config.json 不能 :ro 挂载**(Marzban 要写回),且渲染后含 Reality 私钥不入库。
- **marzban 容器内没有 `curl`/`pkill`/`ps`**。要 curl 容器内服务,从宿主机经 docker 网络 IP(`172.18.0.x`)访问,或在容器装。
- **第三方机场订阅需 clash UA** 才返回节点(`-A clash.meta`),否则 404。
- 客户名只能英文字母/数字/下划线(中文报 422,已加友好提示)。

## 自检工具

- `relayhub/scripts/trace_chain.py <username>` —— 在服务器上跑,逐跳打印某客户访问链路(规则匹配→入口节点→xray路由→ISP出站→实测出口IP)。需先 `source /opt/relayhub-stack/.env`。
- `relayhub/scripts/add_line.py` —— CLI 开通线路(`--exit-ip` 手填出口IP)。

## 文档索引

- [README.md](README.md) — 总览
- [需求文档.md](需求文档.md) · [技术设计与研发方案.md](技术设计与研发方案.md) · [项目计划.md](项目计划.md)
- [relayhub/README.md](relayhub/README.md) · [deploy/README.md](deploy/README.md)
