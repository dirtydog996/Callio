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
| `CALLIO_STT_BACKEND` | `whisper` | STT backend: `whisper` or `sensevoice` |
| `CALLIO_WHISPER_MODEL` | `base` | Whisper model size (`base`, `small`, `medium`, …) |
| `CALLIO_WHISPER_PRELOAD` | `1` | Preload Whisper at startup |
| `CALLIO_FUNASR_MODEL` | `iic/SenseVoiceSmall` | FunASR model name (used when `stt_backend=sensevoice`) |
| `CALLIO_TTS_BACKEND` | `chatt` | TTS backend: `chatt`, `say`, `edge`, `cosyvoice`, `fish` |
| `CALLIO_TTS_PRELOAD` | `1` | Preload ChatTTS at startup |
| `CALLIO_CHATTTS_HOME` | _(empty)_ | Optional HuggingFace cache dir for ChatTTS weights |
| `CALLIO_EDGE_TTS_VOICE` | `zh-CN-XiaoxiaoNeural` | Voice name for EdgeTTS backend |
| `CALLIO_COSYVOICE_URL` | `http://localhost:9880` | CosyVoice REST API base URL |
| `CALLIO_FISH_SPEECH_URL` | `http://localhost:8080` | Fish Speech REST API base URL |
| `CALLIO_AUDIO_OUT_SAMPLE_RATE` | `16000` | Downlink PCM sample rate to the browser |
| `CALLIO_MAX_PARALLEL_TASKS` | `3` | Max parallel RUNNING tasks per voice session |
| `CALLIO_SUMMARIZE_DEBOUNCE_SEC` | `30` | Auto-summary debounce interval during calls |
| `CALLIO_PROGRESS_INJECT` | `1` | Inject task progress block into voice system prompt |
| `CALLIO_AGENT_BACKEND` | _(empty)_ | Force agent: `hermes`, `openclaw`, `goose`, `aider`, `claude` |
| `CALLIO_AGENT_COMMAND` | _(empty)_ | Custom command with `{task}` placeholder |
| `CALLIO_TASK_TIMEOUT_SEC` | `3600` | Max seconds per background task |
| `CALLIO_GLOBAL_MAX_PARALLEL` | `5` | Max RUNNING tasks across all sessions |
| `CALLIO_EXECUTE_MAX_RETRIES` | `3` | Retries for EXECUTE agent runs |
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
| SenseVoice / FunASR | `~/.cache/modelscope/` |

下载完成后，重启服务只需从缓存加载，无需重新联网。

### STT backends

| Backend | 说明 | 安装 |
|---------|------|------|
| **faster-whisper**（默认） | 通用多语言，CPU 可运行 | 已含在 `requirements.txt` |
| **SenseVoice** | 中文识别准确率更高，含情绪感知 | `pip install funasr modelscope` |

```bash
# 启用 SenseVoice
export CALLIO_STT_BACKEND=sensevoice
export CALLIO_FUNASR_MODEL=iic/SenseVoiceSmall   # 首次运行自动下载 ~300 MB
```

### TTS backends

TTS **运行在服务端**，浏览器/手机只播放下行 PCM。

| Backend | 说明 | 安装 / 启动 |
|---------|------|------------|
| **ChatTTS**（默认） | 对话场景，中文自然度优于 `say` | 已含在 `requirements.txt` |
| **macOS say** | 系统 TTS，零依赖回退 | 内置，macOS 专属 |
| **EdgeTTS** | 微软 Edge TTS 云服务，跨平台，速度快 | `pip install edge-tts` + 需 `ffmpeg` |
| **CosyVoice** | 高品质本地 TTS，通过 REST API 对接 | 需单独启动 CosyVoice 服务器 |
| **Fish Speech** | 高品质本地 TTS，通过 REST API 对接 | 需单独启动 Fish Speech 服务器 |

#### EdgeTTS 快速接入

```bash
pip install edge-tts
# macOS: brew install ffmpeg  |  Ubuntu: apt install ffmpeg
export CALLIO_TTS_BACKEND=edge
export CALLIO_EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural  # 可选其他微软中文音色
```

可用中文音色示例：`zh-CN-XiaoxiaoNeural`（女声）、`zh-CN-YunxiNeural`（男声）、`zh-TW-HsiaoChenNeural`（台湾）

#### CosyVoice 快速接入

```bash
# 1. 启动 CosyVoice 服务器（独立环境）
git clone https://github.com/FunAudioLLM/CosyVoice
cd CosyVoice && pip install -r requirements.txt
python runtime/python/fastapi/server.py --port 9880

# 2. 配置 Callio 使用 CosyVoice
export CALLIO_TTS_BACKEND=cosyvoice
export CALLIO_COSYVOICE_URL=http://localhost:9880
```

#### Fish Speech 快速接入

```bash
# 1. 启动 Fish Speech 服务器（独立环境）
pip install fish-speech
python -m tools.api_server --listen 0.0.0.0:8080 \
  --llama-checkpoint-path checkpoints/fish-speech-1.5

# 2. 配置 Callio 使用 Fish Speech
export CALLIO_TTS_BACKEND=fish
export CALLIO_FISH_SPEECH_URL=http://localhost:8080
```

### Agent backends（编码 / 日常任务执行）

Callio 支持多种开源 AI Agent CLI 工具执行后台任务。启动时自动探测，也可通过环境变量强制指定。

| Agent | 说明 | 安装 |
|-------|------|------|
| **hermes** | 通用任务执行框架 | 参见 Hermes 官方文档 |
| **openclaw** | 本地化代码 Agent | 参见 OpenClaw 官方文档 |
| **goose** | Block 开源 AI Agent，支持代码与日常任务 | `pip install goose-ai` 或参见官方文档 |
| **aider** | 流行的 AI 结对编程工具 | `pip install aider-chat` |
| **claude** | Anthropic Claude CLI（`claude code`） | `npm install -g @anthropic-ai/claude-code` |

```bash
# 自动探测（推荐），按 hermes → openclaw → goose → aider → claude 顺序查找
# 无需设置，安装任意一个即可

# 强制指定
export CALLIO_AGENT_BACKEND=aider

# 完全自定义命令（{task} 会被替换为任务描述）
export CALLIO_AGENT_COMMAND="aider --yes-always --message {task}"
```

**日常任务 vs 代码任务**：Agent Resolver 内部区分 `daily`（日常操作）和代码任务，选择合适的 CLI 参数组合。目前所有后端均使用相同的 `--task` 参数；如需为特定后端定制，可通过 `CALLIO_AGENT_COMMAND` 完全控制。

## Mobile testing (iPhone / Android)

手机通过局域网 HTTP 扫码无法使用麦克风，需 HTTPS：

```bash
./scripts/start-mobile-https.sh
```

- 手机测试：[docs/mobile-testing.md](docs/mobile-testing.md)
- 全双工语音架构：[docs/voice-full-duplex.md](docs/voice-full-duplex.md)
- 迭代优化路线图：[docs/iteration-roadmap.md](docs/iteration-roadmap.md)

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
- `GET /api/v1/sessions/{session_id}/tasks` — session tasks, progress, events
- `POST /api/v1/sessions/{session_id}/tasks/confirm` — confirm proposed tasks
- `POST /api/v1/sessions/{session_id}/tasks/cancel` — cancel proposed tasks
- `POST /api/v1/tasks/{node_id}/cancel` — stop a RUNNING task
- `GET /api/v1/tasks/{node_id}/runs` — task execution logs

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

# 端到端语音冒烟（需本机 say + Ollama + 服务已启动）
./venv/bin/python scripts/e2e-voice-test.py
./venv/bin/python scripts/e2e-voice-test.py --two-round-resume
```

### Session 续聊

- 浏览器：开始对话前在下拉框选择历史会话
- WebSocket：`ws://host/ws?resume_session_id=<uuid>`
- API：`GET /api/v1/sessions/{session_id}` 查看历史转写与摘要
