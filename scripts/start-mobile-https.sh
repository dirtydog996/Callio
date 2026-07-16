#!/usr/bin/env bash
# mkcert + HTTPS — one-command Callio startup for LAN mobile testing
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
    echo "mkcert not found — installing via Homebrew..."
    brew install mkcert
    return 0
  fi
  echo "Error: mkcert not found."
  echo "macOS: brew install mkcert"
  echo "Other systems: https://github.com/FiloSottile/mkcert#installation"
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

echo "==> Installing/updating mkcert local CA (may prompt for password on first run)"
mkcert -install

mkdir -p "$CERT_DIR"
LAN_IP="$(detect_lan_ip)"
echo "==> LAN IP: $LAN_IP"

if [[ ! -f "$CERT_FILE" || ! -f "$KEY_FILE" || "$(cat "$LAN_IP_FILE" 2>/dev/null || true)" != "$LAN_IP" ]]; then
  echo "==> Generating HTTPS certificate ($LAN_IP, localhost, 127.0.0.1)"
  mkcert -cert-file "$CERT_FILE" -key-file "$KEY_FILE" "$LAN_IP" localhost 127.0.0.1
  echo "$LAN_IP" > "$LAN_IP_FILE"
else
  echo "==> Reusing existing certificate: $CERT_FILE"
fi

export CALLIO_SSL_CERT="$CERT_FILE"
export CALLIO_SSL_KEY="$KEY_FILE"

echo ""
echo "==> Starting Callio (HTTPS) — scan the QR code in the terminal with your phone"
echo "    iPhone: trust the mkcert root CA via Settings → General → About → Certificate Trust Settings"
echo "    See docs/mobile-testing.md for details"
echo ""

exec "$PYTHON" -m callio "$@"
