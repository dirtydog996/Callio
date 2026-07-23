# Callio configuration examples

This folder contains ready-to-copy examples for common LLM/voice setups.

## 1) Local setup with Ollama

- Path: `examples/01-local-ollama/.env.example`
- Best for local/private development.
- Trade-off: performance depends on local CPU/GPU/RAM.

## 2) DeepSeek / Qwen / OpenAI provider setups

- Path: `examples/02-remote-llm-providers/`
- Includes:
  - `.env.openai.example`
  - `.env.deepseek.example`
  - `.env.qwen.example`
- DeepSeek and Qwen are configured through `openai_compatible` mode.

## 3) More efficient voice (ASR/TTS) setups

- Path: `examples/03-efficient-voice/.env.example`
- Shows higher-performance STT/TTS combinations (`sensevoice`, `edge`, `cosyvoice`, `fish`).

## Quick usage

```bash
cp examples/01-local-ollama/.env.example .env
# or choose another example from examples/02-* / examples/03-*
```

Then start Callio as usual.
