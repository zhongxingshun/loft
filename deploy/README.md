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

## 首次运行需验证的两点

| # | 验证 | 方法 |
|---|---|---|
| 1 | **用户 email 格式**（决定分流是否生效） | `docker compose exec marzban marzban cli ...` 或看 xray 日志里 email 字段，按需校正路由匹配 |
| 2 | **出站护栏生效** | 客户连上后，确认无法访问 `127.0.0.1` / 内网 / `169.254.169.254` / 出站 25 |

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
