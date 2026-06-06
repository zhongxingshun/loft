#!/usr/bin/env bash
# 生成 VLESS-Reality 密钥并写入 deploy/xray_config.json (由模板渲染)。
# 用 Marzban 镜像内置的 xray 生成密钥, 无需本机装 xray。
#
# 用法:  bash deploy/setup-reality.sh
set -euo pipefail

cd "$(dirname "$0")/.."
TEMPLATE="deploy/xray_config.template.json"
OUT="deploy/xray_config.json"

if [[ -f "$OUT" ]]; then
  read -r -p "$OUT 已存在, 覆盖并重新生成密钥? [y/N] " ans
  [[ "${ans:-N}" =~ ^[Yy]$ ]] || { echo "已取消"; exit 0; }
fi

echo "[1/3] 生成 Reality 密钥对..."
KEYS="$(docker run --rm gozargah/marzban:latest xray x25519)"
PRIV="$(echo "$KEYS" | sed -n 's/.*[Pp]rivate key: *//p' | tr -d '[:space:]')"
PUB="$(echo "$KEYS"  | sed -n 's/.*[Pp]ublic key: *//p'  | tr -d '[:space:]')"
SID="$(openssl rand -hex 4)"

if [[ -z "$PRIV" || -z "$PUB" ]]; then
  echo "密钥解析失败, 原始输出:"; echo "$KEYS"; exit 1
fi

echo "[2/3] 渲染 $OUT ..."
sed -e "s|__REALITY_PRIVATE_KEY__|$PRIV|" \
    -e "s|__REALITY_SHORT_ID__|$SID|" \
    "$TEMPLATE" > "$OUT"
chmod 600 "$OUT"

echo "[3/3] 完成。"
echo "----------------------------------------------------------------"
echo "Reality 公钥 (public key, 客户端/订阅需要, Marzban 会自动带上):"
echo "  $PUB"
echo "shortId: $SID   |   serverNames(SNI): www.microsoft.com"
echo "如需更换伪装目标站, 编辑 $TEMPLATE 的 dest/serverNames 后重跑。"
echo "----------------------------------------------------------------"
