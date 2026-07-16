# Callio

![Callio Logo](app/shared/callio-logo.svg)

Call your PC, talk to your agent, and let it handle the I/O.

I just called my computer from the subway, asked Callio to render a video and organize my documents, and it called me back when it was done. Callio is now open-source!

Callio is a voice-first autonomous OS companion built with a modular Python service architecture. It combines real-time voice interaction, multi-client access (Web/Mobile/CLI), and async task execution through pluggable agent backends.

## Project Description

Callio provides:

- Full-duplex voice interaction over WebSocket
- Session-aware task planning and execution
- Multi-client access under a unified `app/` workspace
- Configurable STT/TTS pipelines and LLM runtime
- Extensible agent backend selection for coding and daily tasks

Core modules:

- `callio/config` — runtime settings and environment configuration
- `callio/core` — FastAPI APIs, SQLite state, memory hub
- `callio/voice` — voice pipeline and audio backend integrations
- `callio/worker` — task dispatch, agent resolution, sandbox runner scaffolding
- `callio/meta` — rollout/sanity-check scaffolding
- `app/web`, `app/mobile`, `app/cli`, `app/shared` — user-facing clients

## Features

- Voice-first interaction with server-side STT/TTS orchestration
- Web, mobile, and CLI clients with shared frontend assets
- Background task orchestration with progress tracking and logs
- Session resume support for continuous conversations
- Pluggable STT backends (`whisper`, `sensevoice`)
- Pluggable TTS backends (`chatt`, `say`, `edge`, `cosyvoice`, `fish`)
- Pluggable agent backends (`hermes`, `openclaw`, `goose`, `aider`, `claude`)
- Pluggable LLM providers (`ollama`, `openai`, `anthropic`, `gemini`, `openai_compatible`)

## Feature List

- [x] FastAPI service with REST + WebSocket endpoints
- [x] Multi-client routing (`/app/web`, `/app/mobile`, `/app/cli`)
- [x] Unified task dispatch and execution logging
- [x] Voice session history and resume support
- [x] Environment-driven backend switching
- [x] Mobile HTTPS helper script for microphone compatibility

## Quick Start

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt

# Optional: HuggingFace mirror (recommended for CN network environments)
export CALLIO_HF_ENDPOINT=https://hf-mirror.com

# Optional: verify ChatTTS dependencies
./scripts/check-tts-deps.sh

# Start service
./venv/bin/python -m callio
```

Use Python from `venv` to avoid incompatible dependency resolution from system/conda environments.

## Usage

### Service Startup

```bash
./venv/bin/python -m callio
```

Optional startup flags:

```bash
./venv/bin/python -m callio --no-qr
```

### ASGI Startup

```bash
./venv/bin/uvicorn callio.app:app --host 0.0.0.0 --port 8000
```

### CLI Examples

```bash
python app/cli/main.py health
python app/cli/main.py sessions
python app/cli/main.py dispatch --title "Plan tasks" --description "Break current work into background tasks"
```

### Client Entrypoints

- Web: `/app/web/index.html`
- Mobile: `/app/mobile/index.html`
- Legacy alias: `/static/index.html`

## Configuration

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CALLIO_STT_BACKEND` | `whisper` | STT backend (`whisper`, `sensevoice`) |
| `CALLIO_TTS_BACKEND` | `chatt` | TTS backend (`chatt`, `say`, `edge`, `cosyvoice`, `fish`) |
| `CALLIO_AGENT_BACKEND` | _(empty)_ | Force agent backend (`hermes`, `openclaw`, `goose`, `aider`, `claude`) |
| `CALLIO_AGENT_COMMAND` | _(empty)_ | Custom command template (`{task}` placeholder) |
| `CALLIO_LLM_PROVIDER` | `ollama` | LLM provider (`ollama`, `openai`, `anthropic`, `gemini`, `openai_compatible`) |
| `CALLIO_LLM_MODEL` | `qwen2.5:7b` | Model name for the selected LLM provider |
| `CALLIO_LLM_API_KEY` | _(empty)_ | API key for the selected provider (falls back to `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) |
| `CALLIO_LLM_BASE_URL` | _(empty)_ | Base URL override for `openai_compatible` or to route any provider through a proxy |
| `CALLIO_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama endpoint (used when `CALLIO_LLM_PROVIDER=ollama`; kept for backward compat) |
| `CALLIO_NOTIFY_WECHAT_WEBHOOK` | _(empty)_ | WeChat webhook URL for end-of-session summary notifications |
| `CALLIO_NOTIFY_FEISHU_WEBHOOK` | _(empty)_ | Feishu webhook URL for end-of-session summary notifications |
| `CALLIO_NOTIFY_DISCORD_WEBHOOK` | _(empty)_ | Discord webhook URL for end-of-session summary notifications |
| `CALLIO_NOTIFY_TELEGRAM_WEBHOOK` | _(empty)_ | Telegram webhook URL for end-of-session summary notifications |
| `CALLIO_NOTIFY_TIMEOUT_SEC` | `8` | Timeout (seconds) for notification webhook requests |
| `CALLIO_PORT` | `8000` | Service port |
| `CALLIO_HOST` | `0.0.0.0` | Service bind host |
| `CALLIO_APP_DIR` | `./app` | Top-level client workspace |

See source for all configuration options: `callio/config/settings.py`.

## API and WebSocket Endpoints

Main endpoints:

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/dispatch`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}/tasks`
- `POST /api/v1/sessions/{session_id}/tasks/confirm`
- `POST /api/v1/sessions/{session_id}/tasks/cancel`
- `POST /api/v1/tasks/{node_id}/cancel`
- `GET /api/v1/tasks/{node_id}/runs`
- `WS /ws/status`
- `WS /ws`

## Validation

```bash
./venv/bin/python -m compileall callio
python -m unittest discover tests
```

Optional voice E2E smoke tests:

```bash
./venv/bin/python scripts/e2e-voice-test.py
./venv/bin/python scripts/e2e-voice-test.py --two-round-resume
```

## Update Status

### Latest updates

- Unified user clients under `app/` (`web`, `mobile`, `cli`, `shared`)
- Runtime bootstrap standardized to `python -m callio` (`callio/app.py`, `callio/__main__.py`)
- Expanded pluggable voice/agent backend support
- Session/task APIs improved for progress, confirm/cancel, and resume workflows

### Docs

- User clients: [`docs/user-clients.md`](docs/user-clients.md)
- Mobile HTTPS testing: [`docs/mobile-testing.md`](docs/mobile-testing.md)
- Full-duplex voice architecture: [`docs/voice-full-duplex.md`](docs/voice-full-duplex.md)
- Iteration roadmap: [`docs/iteration-roadmap.md`](docs/iteration-roadmap.md)

## License

This project currently does not include an explicit open-source license file in the repository root. Add one before public distribution if needed.
