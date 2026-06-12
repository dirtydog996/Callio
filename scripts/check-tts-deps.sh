#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT_DIR}/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 venv，请先: python -m venv venv && ./venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "Python: $PYTHON"
"$PYTHON" - <<'PY'
import sys

print("version:", sys.version.split()[0])

try:
    import transformers
    from transformers import LlamaModel
    print("transformers:", transformers.__version__, "OK")
except ImportError as e:
    print("transformers: FAIL -", e)
    print("修复: ./venv/bin/pip install 'transformers>=4.41,<5'")
    sys.exit(1)

try:
    import ChatTTS
    print("ChatTTS: OK")
except ImportError as e:
    print("ChatTTS: FAIL -", e)
    sys.exit(1)

print("\n依赖检查通过。启动: ./venv/bin/python -m callio")
PY
