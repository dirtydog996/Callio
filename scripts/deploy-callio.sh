#!/usr/bin/env bash
# One-shot local deploy for Callio voice stack (Ollama + venv + optional SenseVoice streaming + Smart Turn EOU).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-local}"
MODEL="${CALLIO_LLM_MODEL:-qwen2.5:7b}"
VENV="${ROOT}/venv"
PYTHON="${VENV}/bin/python"

echo "==> Callio deploy ($MODE)"

_pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
  elif command -v python >/dev/null 2>&1; then
    echo python
  else
    echo "ERROR: python3 not found; install Python 3.10+" >&2
    exit 1
  fi
}

venv_is_healthy() {
  [[ -x "$PYTHON" ]] || return 1
  "$PYTHON" -c "import sys" >/dev/null 2>&1
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
"$PYTHON" -m pip install -r requirements.txt

# Pipecat Smart Turn v3 uses onnxruntime (bundled ONNX in pipecat package).
"$PYTHON" -m pip install 'onnxruntime>=1.17.0' >/dev/null || true

if [[ "${CALLIO_STT_BACKEND:-}" == "sensevoice" || "${CALLIO_FUNASR_STREAMING:-1}" == "1" ]]; then
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

if command -v ollama >/dev/null 2>&1; then
  echo "==> Pulling Ollama model: $MODEL"
  ollama pull "$MODEL" || true
else
  echo "WARN: ollama not found; start LLM separately"
fi

if [[ ! -s "${ROOT}/.env" ]] || ! grep -q CALLIO_LLM_MODEL "${ROOT}/.env"; then
  echo "TIP: run '$PYTHON -m callio setup' to customize LLM/STT/TTS"
fi

echo "==> Running unit tests"
"$PYTHON" -m pytest tests/ -q --tb=no || {
  echo "WARN: some tests failed (optional models may be missing in CI)"
}

echo "==> Starting Callio on :${CALLIO_PORT:-8000}"
exec "$PYTHON" -m callio
