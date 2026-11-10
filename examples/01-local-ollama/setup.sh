#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export CALLIO_LLM_MODEL="${1:-qwen2.5:7b}"
export CALLIO_STT_BACKEND="${CALLIO_STT_BACKEND:-sensevoice}"
export CALLIO_FUNASR_STREAMING="${CALLIO_FUNASR_STREAMING:-1}"
export CALLIO_SEMANTIC_EOU="${CALLIO_SEMANTIC_EOU:-1}"

exec "${ROOT}/scripts/deploy-callio.sh" local
