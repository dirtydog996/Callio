Call your PC, talk to your Agent, and let it handle the I/O.

Callio is a voice-first autonomous OS companion built around a modular Python service architecture:

- `callio/config` — runtime settings
- `callio/core` — FastAPI API, SQLite state, memory hub
- `callio/web` — browser voice client (`static/index.html`)
- `callio/voice` — Pipecat voice pipeline (Whisper STT, ChatTTS, Ollama LLM)
- `callio/worker` — async task dispatching, sandbox runner scaffolding
- `callio/meta` — shadow rollout and sanity-check scaffolding

## Quick start

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt

# 国内建议设置 HuggingFace 镜像（Whisper / ChatTTS 首次下载）
export CALLIO_HF_ENDPOINT=https://hf-mirror.com

# 检查语音依赖（ChatTTS + transformers 版本）
./scripts/check-tts-deps.sh

# 启动服务
./venv/bin/python -m callio
```

首次启动会预加载 Whisper 与 ChatTTS，模型下载可能需要数分钟；之后从本地缓存加载。

跳过终端二维码：`./venv/bin/python -m callio --no-qr`

> **请使用 `venv` 内的 Python 启动。** 若用 conda / 系统 `python`，可能加载到不兼容的 `transformers` 版本，导致 ChatTTS 回退到 macOS `say`。

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CALLIO_HF_ENDPOINT` | _(empty)_ | HuggingFace mirror, e.g. `https://hf-mirror.com` |
| `CALLIO_WHISPER_MODEL` | `base` | Whisper model size (`base`, `small`, `medium`, …) |
| `CALLIO_WHISPER_PRELOAD` | `1` | Preload Whisper at startup |
| `CALLIO_TTS_BACKEND` | `chatt` | TTS backend: `chatt` (ChatTTS on Mac) or `say` (macOS fallback) |
| `CALLIO_TTS_PRELOAD` | `1` | Preload ChatTTS at startup |
| `CALLIO_CHATTTS_HOME` | _(empty)_ | Optional HuggingFace cache dir for ChatTTS weights |
| `CALLIO_AUDIO_OUT_SAMPLE_RATE` | `16000` | Downlink PCM sample rate to the browser |
| `CALLIO_LLM_MODEL` | `qwen2.5:7b` | Ollama model name |
| `CALLIO_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible API |
| `CALLIO_SSL_CERT` | _(empty)_ | HTTPS certificate path (required for mobile microphone) |
| `CALLIO_SSL_KEY` | _(empty)_ | HTTPS private key path |
| `CALLIO_PORT` | `8000` | Server port |
| `CALLIO_HOST` | `0.0.0.0` | Bind address |

### Model cache

| Model | Cache location |
|-------|----------------|
| Whisper | `~/.cache/huggingface/hub/` |
| ChatTTS | `~/.cache/huggingface/hub/models--2Noise--ChatTTS/` |

下载完成后，重启服务只需从缓存加载，无需重新联网。

### TTS backends

TTS **运行在 Mac 服务端**，手机只采集麦克风并播放下行 PCM。

| Backend | When to use |
|---------|-------------|
| **ChatTTS**（默认） | 对话场景，中文自然度优于系统 `say` |
| **macOS say** | `CALLIO_TTS_BACKEND=say`，或 ChatTTS 加载失败时自动回退 |

曾评估 CosyVoice / Fish Speech：音质好，但 Mac 上推理慢或集成成本高，不适合实时全双工通话。

## Mobile testing (iPhone / Android)

手机通过局域网 HTTP 扫码无法使用麦克风，需 HTTPS：

```bash
./scripts/start-mobile-https.sh
```

- 手机测试：[docs/mobile-testing.md](docs/mobile-testing.md)
- 全双工语音架构：[docs/voice-full-duplex.md](docs/voice-full-duplex.md)

## Run locally (ASGI)

```bash
./venv/bin/uvicorn callio.app:app --host 0.0.0.0 --port 8000
```

启用 HTTPS 时设置 `CALLIO_SSL_CERT` / `CALLIO_SSL_KEY`，或使用 `scripts/start-mobile-https.sh`。

## Main endpoints

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/dispatch`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `WS /ws/status`
- `WS /ws` — full-duplex voice (PCM + JSON)

## Troubleshooting

### ChatTTS 预加载失败 / 回退到 `say`

```bash
./scripts/check-tts-deps.sh
```

若提示 `LlamaModel` 导入失败：

```bash
./venv/bin/pip install 'transformers>=4.41,<5' --force-reinstall
./scripts/check-tts-deps.sh
```

`transformers` 5.x 与 ChatTTS 不兼容，必须用 4.x。

### 模型下载慢或超时

```bash
export CALLIO_HF_ENDPOINT=https://hf-mirror.com
./venv/bin/python -m callio
```

首次 ChatTTS 下载约 14 个文件，国内网络可能需要 10 分钟左右。

### 语音相关脚本

| Script | Purpose |
|--------|---------|
| `scripts/check-tts-deps.sh` | 检查 Python / transformers / ChatTTS |
| `scripts/start-mobile-https.sh` | mkcert + HTTPS 一键启动 |

## Validation

```bash
./venv/bin/python -m compileall callio
./venv/bin/python - <<'PY'
from callio.app import app
print(len(app.routes))
PY
```
