#!/usr/bin/env bash
# 方案一：mkcert + HTTPS，一键启动 Callio 供手机局域网测试
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CERT_DIR="$ROOT_DIR/certs"
CERT_FILE="$CERT_DIR/callio.pem"
KEY_FILE="$CERT_DIR/callio-key.pem"
LAN_IP_FILE="$CERT_DIR/.lan-ip"

if [[ -f "$ROOT_DIR/venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/venv/bin/python"
elif [[ -f "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

ensure_mkcert() {
  if command -v mkcert >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$(uname -s)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    echo "未检测到 mkcert，正在通过 Homebrew 安装..."
    brew install mkcert
    return 0
  fi
  echo "错误: 未找到 mkcert。"
  echo "macOS: brew install mkcert"
  echo "其他系统: https://github.com/FiloSottile/mkcert#installation"
  exit 1
}

detect_lan_ip() {
  local ip=""
  for iface in en0 en1; do
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    if [[ -n "$ip" ]]; then
      echo "$ip"
      return 0
    fi
  done
  "$PYTHON" - <<'PY'
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8", 80))
    print(s.getsockname()[0])
finally:
    s.close()
PY
}

ensure_mkcert

echo "==> 安装/更新 mkcert 本地 CA（首次可能需要输入密码）"
mkcert -install

mkdir -p "$CERT_DIR"
LAN_IP="$(detect_lan_ip)"
echo "==> 局域网 IP: $LAN_IP"

if [[ ! -f "$CERT_FILE" || ! -f "$KEY_FILE" || "$(cat "$LAN_IP_FILE" 2>/dev/null || true)" != "$LAN_IP" ]]; then
  echo "==> 生成 HTTPS 证书 ($LAN_IP, localhost, 127.0.0.1)"
  mkcert -cert-file "$CERT_FILE" -key-file "$KEY_FILE" "$LAN_IP" localhost 127.0.0.1
  echo "$LAN_IP" > "$LAN_IP_FILE"
else
  echo "==> 复用已有证书: $CERT_FILE"
fi

export CALLIO_SSL_CERT="$CERT_FILE"
export CALLIO_SSL_KEY="$KEY_FILE"

echo ""
echo "==> 启动 Callio (HTTPS)，手机请扫终端二维码"
echo "    iPhone 首次使用需在「设置 → 证书信任设置」中信任 mkcert 根证书"
echo "    详见 docs/mobile-testing.md"
echo ""

exec "$PYTHON" -m callio "$@"
