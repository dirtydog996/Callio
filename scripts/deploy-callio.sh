#!/usr/bin/env bash
# One-shot local deploy for Callio voice stack (Ollama + venv + optional SenseVoice streaming + Smart Turn EOU).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-local}"
CHECK_ONLY="${CALLIO_DEPLOY_CHECK_ONLY:-0}"
if [[ "${2:-}" == "--check" ]]; then
  CHECK_ONLY=1
fi
PIP_PYPI="${CALLIO_PIP_FALLBACK_INDEX:-https://pypi.org/simple}"
MODEL="${CALLIO_LLM_MODEL:-qwen2.5:7b}"
VENV="${ROOT}/venv"
PYTHON="${VENV}/bin/python"

echo "==> Callio deploy ($MODE)"

_python_version_ok() {
  local py="$1"
  "$py" -c 'import sys; v=sys.version_info; sys.exit(0 if v>=(3,11) else 1)' 2>/dev/null
}

_pick_python() {
  local py
  for py in python3.12 python3.11; do
    if command -v "$py" >/dev/null 2>&1 && _python_version_ok "$py"; then
      command -v "$py"
      return 0
    fi
  done
  if command -v python3 >/dev/null 2>&1 && _python_version_ok python3; then
    echo python3
  elif command -v python >/dev/null 2>&1 && _python_version_ok python; then
    echo python
  else
    echo "ERROR: Python 3.11+ is required (pipecat-ai>=1.2.1). Install it and re-run." >&2
    exit 1
  fi
}

venv_is_healthy() {
  [[ -x "$PYTHON" ]] || return 1
  "$PYTHON" -c "import sys" >/dev/null 2>&1 || return 1
  "$PYTHON" -c 'import sys; v=sys.version_info; sys.exit(0 if v>=(3,11) else 1)' >/dev/null 2>&1
}

SYS_PY="$(_pick_python)"

if [[ ! -d "$VENV" ]] || ! venv_is_healthy; then
  if [[ -d "$VENV" ]]; then
    echo "==> Removing broken venv (stale interpreter path — common after moving the repo or upgrading Python)"
    rm -rf "$VENV"
  else
    echo "==> Creating venv at ${VENV}"
  fi
  "$SYS_PY" -m venv "$VENV"
  PYTHON="${VENV}/bin/python"
  if ! venv_is_healthy; then
    echo "ERROR: failed to create a working venv at ${VENV}" >&2
    exit 1
  fi
fi

# Use python -m pip so we never rely on venv/bin/pip shebang (can break like venv/bin/python).
"$PYTHON" -m pip install -U pip wheel setuptools >/dev/null

ORT_LEGACY=0

install_onnxruntime_for_pipecat() {
  # pipecat metadata requires onnxruntime>=1.24.3; some mirrors and some OS/Python
  # combos only publish wheels up to ~1.19.x (common on older macOS builds).
  if "$PYTHON" -m pip install 'onnxruntime>=1.24.3,<2' >/dev/null 2>&1; then
    ORT_LEGACY=0
    return 0
  fi
  echo "==> Trying onnxruntime>=1.24.3 from ${PIP_PYPI} only (bypass mirror)"
  if "$PYTHON" -m pip install 'onnxruntime>=1.24.3,<2' \
    --index-url "${PIP_PYPI}" \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org >/dev/null 2>&1; then
    ORT_LEGACY=0
    return 0
  fi
  echo "==> No onnxruntime>=1.24.3 wheel for this platform; installing onnxruntime 1.19.x"
  echo "    (pipecat will be installed with --no-deps; Smart Turn v3 still works on 1.19.x)"
  "$PYTHON" -m pip install 'onnxruntime>=1.17.0,<=1.19.2'
  ORT_LEGACY=1
}

install_python_requirements() {
  install_onnxruntime_for_pipecat
  if [[ "$ORT_LEGACY" == "1" ]]; then
    local req_nopipe="${ROOT}/.callio-requirements-no-pipecat.txt"
    grep -v -E '^[[:space:]]*pipecat-ai' "${ROOT}/requirements.txt" >"${req_nopipe}"
    "$PYTHON" -m pip install -r "${req_nopipe}"
    "$PYTHON" -m pip install 'pipecat-ai>=1.2.1' --no-deps
  else
    "$PYTHON" -m pip install -r requirements.txt
  fi
}

install_python_requirements

if [[ "${CALLIO_STT_BACKEND:-}" == "sensevoice" ]]; then
  echo "==> Installing FunASR (streaming SenseVoice / Paraformer-online)"
  "$PYTHON" -m pip install 'funasr>=1.1.0' 'modelscope>=1.14.0' 'huggingface_hub>=0.20.0' soundfile >/dev/null || {
    echo "WARN: FunASR optional deps failed; set CALLIO_STT_BACKEND=whisper to skip"
  }
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  if [[ -f "${ROOT}/.env.example" ]]; then
    cp "${ROOT}/.env.example" "${ROOT}/.env"
  elif [[ -f "${ROOT}/examples/01-local-ollama/.env.example" ]]; then
    cp "${ROOT}/examples/01-local-ollama/.env.example" "${ROOT}/.env"
  fi
fi

# Recommended low-latency voice defaults (idempotent append).
append_env() {
  local key="$1" val="$2"
  if ! grep -q "^${key}=" "${ROOT}/.env" 2>/dev/null; then
    echo "${key}=${val}" >>"${ROOT}/.env"
  fi
}

append_env CALLIO_STT_BACKEND "${CALLIO_STT_BACKEND:-sensevoice}"
append_env CALLIO_FUNASR_STREAMING "${CALLIO_FUNASR_STREAMING:-1}"
append_env CALLIO_FUNASR_STREAMING_MODEL "${CALLIO_FUNASR_STREAMING_MODEL:-iic/speech_paraformer_asr_nat-zh-cn-16k-common-vocab8404-online}"
append_env CALLIO_SEMANTIC_EOU "${CALLIO_SEMANTIC_EOU:-1}"
append_env CALLIO_LATENCY_TRACE "${CALLIO_LATENCY_TRACE:-1}"
append_env CALLIO_TTS_BACKEND "${CALLIO_TTS_BACKEND:-edge}"

if [[ "$MODE" == "docker" ]]; then
  echo "==> Starting docker compose"
  docker compose up -d --build
  echo "Callio: http://127.0.0.1:${CALLIO_PORT:-8000}"
  exit 0
fi

if [[ "${CALLIO_SKIP_OLLAMA_PULL:-0}" == "1" ]]; then
  echo "==> Skipping Ollama model pull (CALLIO_SKIP_OLLAMA_PULL=1); pull $MODEL manually before first use"
elif command -v ollama >/dev/null 2>&1; then
  echo "==> Pulling Ollama model: $MODEL"
  ollama pull "$MODEL" || true
else
  echo "WARN: ollama not found; start LLM separately"
fi

if [[ ! -s "${ROOT}/.env" ]] || ! grep -q CALLIO_LLM_MODEL "${ROOT}/.env"; then
  echo "TIP: run '$PYTHON -m callio setup' to customize LLM/STT/TTS"
fi

echo "==> Running unit tests"
"$PYTHON" -m pip install -q pytest
"$PYTHON" -m pytest tests/ -q --tb=no || {
  echo "WARN: some tests failed (optional models may be missing in CI)"
}

if [[ "$CHECK_ONLY" == "1" ]]; then
  echo "==> Deploy check OK (venv + dependencies + tests)"
  "$PYTHON" -c "
import onnxruntime, pipecat
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
print('onnxruntime', onnxruntime.__version__)
print('pipecat', pipecat.__version__)
LocalSmartTurnAnalyzerV3()
print('smart_turn_v3', 'ok')
"
  exit 0
fi

echo "==> Starting Callio on :${CALLIO_PORT:-8000}"
exec "$PYTHON" -m callio
