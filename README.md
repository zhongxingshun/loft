# Loft — ISP IP 中转 / 转售服务

把静态住宅 **ISP(decode/Decodo SOCKS5)** 出口,通过一台中转 VPS 链式转发给客户,每个客户分配一条**专属住宅出口 IP**,并一键生成订阅(Clash / VLESS)。专为 **AI 服务(Claude / ChatGPT / Gemini …)** 防风控场景设计。

```
客户(国内) ──┬─ AI 流量 ──→ 中转节点(VLESS-Reality) ──→ 客户专属 ISP 住宅 IP ──→ Claude/GPT
             │
             └─ 其余流量 ─→ 直连大流量机场(不过中转服务器,省流量) ──→ 目标站
```

## 为什么这么设计

| 诉求 | 方案 |
|---|---|
| AI 账号怕换 IP 被风控 | 每客户**固定专属住宅 IP**,AI 流量专线走它 |
| 中转 VPS 流量贵(2TB) | 非 AI 流量**直连第三方大流量机场**,绕开中转服务器 |
| 国内能稳定连、不被封 | 入站 **VLESS-Reality**(无需域名,伪装 TLS,抗探测) |
| 微信/通话/国内 App 不卡 | DNS `fake-ip-filter` 白名单 + 国内/腾讯直连规则 |
| 快速开通新客户 | RelayHub:填线路 → 自动配 Xray 出站+路由 → 出订阅 |

## 技术栈

| 组件 | 作用 |
|---|---|
| **Marzban** | 用户/订阅面板,管理 Xray |
| **Xray** | 代理核心,VLESS-Reality 入站,按用户分流出站 |
| **RelayHub**(自研 FastAPI) | 开通编排:把 SOCKS5 线路配进 Xray、出站安全护栏、订阅后处理(注入出口IP、合并机场节点做分流) |
| **Caddy** | 反代:`/sub/*` 公网订阅 + `:8443` 面板(TLS+鉴权) |

全部由 `docker compose` 编排,一条命令拉起。

## 快速开始

```bash
# 1. 配置
cp .env.example .env && vim .env          # 填管理员密码、本机IP、大流量机场订阅URL 等
bash deploy/setup-reality.sh              # 生成 Reality 密钥 → deploy/xray_config.json

# 2. 启动
docker compose up -d

# 3. 开通客户(二选一)
#   a) Web 面板: https://<IP>:8443  (Basic Auth)
#   b) CLI:  add_line.py <客户名> <ip:port:user:pass> [--days N --gb N --exit-ip IP]
python relayhub/scripts/add_line.py jeffrey \
    isp.decodo.com:10001:speengd2c8:**** --exit-ip 9.142.76.61
```

详见 [deploy/README.md](deploy/README.md)。

## 分流效果(实测)

| 访问 | 命中规则 | 路径 | 出口 IP |
|---|---|---|---|
| `claude.ai` | 🤖 AI 专线 | 节点 → ISP 住宅 | 客户专属住宅(如 9.142.76.61) |
| `google.com` | 🚀 大流量 | 直连机场 HK | 机场共享(如 45.207.156.18) |
| `weixin.qq.com` | 🎯 全球直连 | 直连 | 本地 |

用 `relayhub/scripts/trace_chain.py <username>` 可在服务器上逐跳追踪任意客户的真实链路。

## 目录结构

```
docker-compose.yml          整套栈编排
deploy/
  clash-template.yml        ★ 分流规则 / DNS / fake-ip-filter (改这里 + 重启 marzban)
  setup-reality.sh          生成 Reality 密钥
  Caddyfile                 反代配置
relayhub/
  app/                      config / parsing / guard / marzban / provisioning / api
  scripts/add_line.py       CLI 开通
  scripts/trace_chain.py    链路追踪自检
  web/index.html            管理面板
需求文档.md / 技术设计与研发方案.md / 项目计划.md   设计文档
CLAUDE.md                   运维手册 / 踩坑记录(改配置流程必读)
```

## 运维要点(详见 [CLAUDE.md](CLAUDE.md))

- **改分流规则**:改 `deploy/clash-template.yml` → rsync → `docker compose restart marzban` → 客户刷新订阅(链接不变)。
- **重启 marzban 不会断已发订阅**(已验证)。
- **出口 IP 由服务器 SOCKS5 出站决定**,与客户端 clash 规则无关;Decodo ISP 一个端口=一个固定住宅 IP。
- 密钥(`.env`、`deploy/certs/`、`deploy/xray_config.json`)**不入库**。

## 安全

- 对公网仅开 `443`(Reality);面板默认仅本地,公网经 Caddy + Basic Auth。
- 出站护栏:封私网/本机/25 端口,防客户回打与滥用。
- 详见 [技术设计与研发方案.md](技术设计与研发方案.md) 安全章节(SEC-*)。
