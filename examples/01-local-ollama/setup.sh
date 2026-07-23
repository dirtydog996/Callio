#!/usr/bin/env bash
set -euo pipefail

MODEL="${1:-qwen2.5:7b}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama is not installed. Install: https://ollama.com"
  exit 1
fi

ollama serve >/dev/null 2>&1 &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" >/dev/null 2>&1 || true' EXIT

ollama pull "$MODEL"
echo "Ready. Use examples/01-local-ollama/.env.example and set CALLIO_LLM_MODEL=$MODEL"
