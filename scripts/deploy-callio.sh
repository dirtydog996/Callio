#!/usr/bin/env bash
# One-shot local deploy for Callio voice stack (Ollama + venv + optional SenseVoice streaming + Smart Turn EOU).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-local}"
MODEL="${CALLIO_LLM_MODEL:-qwen2.5:7b}"
VENV="${ROOT}/venv"
PYTHON="${VENV}/bin/python"
PIP="${VENV}/bin/pip"

echo "==> Callio deploy ($MODE)"

if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi

"$PIP" install -U pip wheel setuptools >/dev/null
"$PIP" install -r requirements.txt

# Pipecat Smart Turn v3 uses onnxruntime (bundled ONNX in pipecat package).
"$PIP" install 'onnxruntime>=1.17.0' >/dev/null || true

if [[ "${CALLIO_STT_BACKEND:-}" == "sensevoice" || "${CALLIO_FUNASR_STREAMING:-1}" == "1" ]]; then
  echo "==> Installing FunASR (streaming SenseVoice / Paraformer-online)"
  "$PIP" install 'funasr>=1.1.0' 'modelscope>=1.14.0' 'huggingface_hub>=0.20.0' soundfile >/dev/null || {
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
