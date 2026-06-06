# 部署指南 —— 一键集成栈

整套服务（**Marzban + Xray + RelayHub**）由 `docker compose` 编排，一条命令拉起。
入站默认 **VLESS-Reality**（无需域名/证书，抗探测强）。

## 前置

- 一台美国 VPS（Ubuntu/Debian），已装 Docker + Docker Compose
- 已完成主机加固（SSH 密钥/防火墙/fail2ban，见 [技术设计与研发方案.md](../技术设计与研发方案.md) C1 阶段一）
- 防火墙放行：`443`（代理）、SSH 端口；**不要**放行 8000/8080

## 部署步骤

```bash
# 1. 克隆
git clone git@github.com:zhongxingshun/loft.git && cd loft

# 2. 配置
cp .env.example .env
vim .env                       # 填 MARZBAN_ADMIN_PASS、LOCAL_IP(本机公网IP)

# 3. 生成 Reality 密钥并渲染 xray 配置 (输出 public key)
bash deploy/setup-reality.sh

# 4. 拉起整栈
docker compose up -d
docker compose logs -f relayhub   # 看到 "[bootstrap] 安全护栏已就位" 即就绪
```

## 访问面板（仅本地，经 SSH 隧道）

面板只监听 `127.0.0.1`（SEC-3），从你的电脑开隧道：

```bash
ssh -L 8080:127.0.0.1:8080 -L 8000:127.0.0.1:8000 user@<VPS> -p <SSH端口>
# 浏览器:
#   RelayHub 开通面板 -> http://127.0.0.1:8080
#   Marzban 原生面板  -> http://127.0.0.1:8000/dashboard
```

## 开通一个客户

- **网页**：RelayHub 面板 → 「＋ 开通新线路」→ 填客户名 + decode 线路串 → 出订阅
- **命令行**：
  ```bash
  docker compose exec relayhub python -m scripts.add_line zhang 1.2.3.4:8080:user:pass --days 30
  ```

## 首次运行：核验分流是否真的命中

开通默认已用**多候选 email 匹配**（同时写入 `客户名` 和 `客户名@VLESS_REALITY`），覆盖常见格式。
客户连上并产生流量后，跑一次**路由核验**，直接从日志看每个客户走了哪个出口：

```bash
docker compose logs marzban --no-color | \
  docker compose exec -T relayhub python -m scripts.verify_routing
```

输出解读：

| OUTBOUND | 判定 | 含义 |
|---|---|---|
| `out-<客户>` | ✅ 分流命中 | 流量确实走该客户的 decode 出口 |
| `block` | 护栏拦截 | 私网/25 被拦（符合预期，SEC-5） |
| `direct` | ⚠️ 未命中分流 | 走了默认出口（VPS 本机 IP），分流失效 |

若某客户被标红走 `direct`，输出里会**显示其真实 email 格式**（例如带 id 前缀的 `7.wang`）。
据此把该格式补进 `relayhub/app/provisioning.py::email_candidates` 即可，重新开通后再核验。

> 这一步把"email 格式对不对"变成了"出口对不对"的直接判定，无需额外客户端。

## 另一项首次验证

| 验证 | 方法 |
|---|---|
| **出站护栏生效** | 客户连上后，确认无法访问 `127.0.0.1` / 内网 / `169.254.169.254` / 出站 25 |

## 告警（可选，到期/流量/线路）

配置 Telegram 后，客户**快到期 / 流量快到上限 / decode 线路探活失败**时自动推送给你。

1. 找 [@BotFather](https://t.me/BotFather) 创建 bot 拿 token；找 [@userinfobot](https://t.me/userinfobot) 拿你的 chat_id
2. 在 `.env` 填：
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=88888888
   ALERT_INTERVAL_MIN=10        # 每10分钟自检推送 (0=关闭)
   ALERT_EXPIRE_DAYS=3          # 剩 3 天内到期就提醒
   ALERT_TRAFFIC_PCT=90         # 流量用到 90% 就提醒
   ```
3. `docker compose up -d` 重启生效。RelayHub 后台定时自检，内存去重不刷屏。

手动预览 / 测试推送：
```bash
docker compose exec relayhub python -m scripts.check_alerts          # 仅预览
docker compose exec relayhub python -m scripts.check_alerts --send   # 测试推送
```
RelayHub 面板左侧 🔔 也会实时显示当前告警条数。

> 配合每客户 `--gb` 上限，能稳稳把总流量压在 VPS 月额度内（如搬瓦工 2TB/月）。

## 组件与端口

| 服务 | 端口 | 暴露 | 说明 |
|---|---|---|---|
| Xray 入站 | 443 | 公网 | VLESS-Reality |
| Marzban 面板 | 8000 | 仅本地 | 原生管理 |
| RelayHub 面板 | 8080 | 仅本地 | 开通/总览/探活 |

## 常用运维

```bash
docker compose ps                       # 状态
docker compose logs -f marzban          # Marzban 日志
docker compose restart relayhub         # 重启 RelayHub
docker compose pull && docker compose up -d   # 升级镜像
docker compose down                     # 停止 (数据保留在 marzban_data 卷)
```

## 切换到 ws+tls (备选)

若你有域名并希望用 `ws+tls` 而非 Reality：替换 `deploy/xray_config.template.json` 的 inbound 为 vless+ws+tls（配证书），并把 compose 里 `RELAYHUB_SHARED_INBOUND_TAG` 改为对应 tag。详见技术设计文档 A4.1。
