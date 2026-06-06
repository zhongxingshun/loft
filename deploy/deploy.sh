#!/usr/bin/env bash
# 一键部署到 VPS (本地执行)。
#
# 用法:
#   deploy/deploy.sh [user@host]
#   SSH_KEY=~/.ssh/id_rsa_lightnode deploy/deploy.sh root@130.94.12.123
#
# 流程: 同步项目 -> 装 Docker+加固 -> 生成 .env(随机管理员密码) -> 生成 Reality 密钥 -> 拉起整栈
# 幂等: 已存在的 .env / Reality 配置不会被覆盖。
set -euo pipefail

HOST="${1:-root@130.94.12.123}"
REMOTE_DIR="/opt/relayhub-stack"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
[[ -n "${SSH_KEY:-}" ]] && SSH_OPTS+=(-i "$SSH_KEY")
ssh_() { ssh "${SSH_OPTS[@]}" "$HOST" "$@"; }

echo "==> 0/5 连通性检查 ($HOST)"
ssh_ 'echo "已连接: $(. /etc/os-release 2>/dev/null && echo $PRETTY_NAME)"'

echo "==> 1/5 同步项目到 $REMOTE_DIR"
# 确保远端有 rsync (传输用)
ssh_ "command -v rsync >/dev/null 2>&1 || (export DEBIAN_FRONTEND=noninteractive; apt-get update -y -q && apt-get install -y -q rsync)"
ssh_ "mkdir -p $REMOTE_DIR"
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '.env' --exclude 'deploy/xray_config.json' \
  -e "ssh ${SSH_OPTS[*]}" \
  "$REPO_DIR/" "$HOST:$REMOTE_DIR/"

echo "==> 2/5 安装 Docker + 基础加固"
ssh_ "bash $REMOTE_DIR/deploy/remote-setup.sh"

echo "==> 3/5 生成 .env (若不存在, 随机管理员密码, LOCAL_IP 自动取本机公网IP)"
ssh_ "bash -s" <<REMOTE
set -e
cd $REMOTE_DIR
if [[ ! -f .env ]]; then
  PASS="\$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
  IP="\$(curl -s4 https://api.ipify.org || hostname -I | awk '{print \$1}')"
  cat > .env <<EOF
MARZBAN_ADMIN_USER=admin
MARZBAN_ADMIN_PASS=\$PASS
LOCAL_IP=\$IP
SUB_URL_PREFIX=http://\$IP
BLOCK_SMTP=true
BLOCK_BITTORRENT=false
ALERT_INTERVAL_MIN=0
EOF
  chmod 600 .env
  echo "  已生成 .env (LOCAL_IP=\$IP)"
else
  grep -q '^SUB_URL_PREFIX=' .env || echo "SUB_URL_PREFIX=http://\$(curl -s4 https://api.ipify.org || hostname -I | awk '{print \$1}')" >> .env
  echo "  .env 已存在, 已确保 SUB_URL_PREFIX"
fi
REMOTE

echo "==> 4/5 生成 Reality 密钥 + Marzban 自签证书 (若已生成则保留)"
ssh_ "cd $REMOTE_DIR && if [[ -f deploy/xray_config.json ]]; then echo '  Reality 已存在, 跳过'; else yes | bash deploy/setup-reality.sh; fi"
ssh_ "cd $REMOTE_DIR && mkdir -p deploy/certs && if [[ -f deploy/certs/marzban.crt ]]; then echo '  证书已存在, 跳过'; else openssl req -x509 -newkey rsa:2048 -nodes -keyout deploy/certs/marzban.key -out deploy/certs/marzban.crt -days 3650 -subj '/CN=marzban' 2>/dev/null && chmod 600 deploy/certs/marzban.key && echo '  自签证书已生成'; fi"

echo "==> 5/5 构建并拉起整栈"
ssh_ "cd $REMOTE_DIR && docker compose up -d --build && sleep 6 && docker compose ps"

echo ""
echo "================ 部署完成 ================"
ssh_ "cd $REMOTE_DIR && echo '管理员账号:' && grep -E 'MARZBAN_ADMIN' .env && echo '' && echo 'RelayHub bootstrap 日志:' && docker compose logs --tail=8 relayhub 2>/dev/null"
cat <<TIP

访问面板 (仅本地监听, 从你的电脑开 SSH 隧道):
  ssh -L 8080:127.0.0.1:8080 -L 8000:127.0.0.1:8000 $HOST
  浏览器 -> RelayHub: http://127.0.0.1:8080   |   Marzban: http://127.0.0.1:8000/dashboard

开通首个客户:
  ssh $HOST "cd $REMOTE_DIR && docker compose exec -T relayhub python -m scripts.add_line zhang <ip:port:user:pass> --days 30"
TIP
