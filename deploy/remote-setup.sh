#!/usr/bin/env bash
# 在 VPS 上执行: 安装 Docker + 基础加固 (幂等)。由 deploy.sh 远程调用, 也可单独跑。
set -euo pipefail

echo "[remote] 系统: $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -a)"

HAS_APT=0; command -v apt-get >/dev/null 2>&1 && HAS_APT=1

# ---- Docker ----
if ! command -v docker >/dev/null 2>&1; then
  echo "[remote] 安装 Docker..."
  curl -fsSL https://get.docker.com | sh
else
  echo "[remote] Docker 已存在: $(docker --version)"
fi
systemctl enable --now docker 2>/dev/null || true

if ! docker compose version >/dev/null 2>&1; then
  echo "[remote] ⚠️ 未检测到 docker compose v2 插件, 请确认 Docker 版本 (get.docker.com 默认已含)。"
fi

# ---- 基础加固 (仅 apt 系) ----
if [[ "$HAS_APT" == "1" ]]; then
  export DEBIAN_FRONTEND=noninteractive
  echo "[remote] 安装 ufw / fail2ban / unattended-upgrades..."
  apt-get update -y -q
  apt-get install -y -q ufw fail2ban unattended-upgrades curl

  # 防火墙: 默认拒绝入站, 放行 SSH(22) + 443(代理) + 80(订阅)。8000/8080 绑 127.0.0.1 不对外。
  ufw allow 22/tcp    >/dev/null
  ufw allow 443/tcp   >/dev/null
  ufw allow 80/tcp    >/dev/null
  ufw default deny incoming  >/dev/null
  ufw default allow outgoing >/dev/null
  yes | ufw enable    >/dev/null 2>&1 || ufw --force enable
  echo "[remote] 防火墙规则:"; ufw status | sed 's/^/    /'

  systemctl enable --now fail2ban 2>/dev/null || true
  echo "[remote] 基础加固完成。"
else
  echo "[remote] ⚠️ 非 apt 系统, 跳过 ufw/fail2ban。请自行配置防火墙仅放行 22 与 443。"
fi
