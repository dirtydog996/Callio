# Callio - Your Voice-First Super Intelligence

🌐 Language: **English** | [简体中文](README.zh-CN.md)

![Callio Logo](app/shared/callio-logo.svg)

> "Talk to your code. Talk to your ideas. Talk to the future."

Callio is a voice-first super-intelligent personal assistant built on large language models, designed to transform how humans collaborate with AI. It is not another voice assistant that only follows commands and gives answers. Callio is an extension of your mind: a second brain you can call anytime, anywhere.

Whether you are driving, cooking, taking a walk, or resting with your eyes closed, you can pick up your phone, call Callio, and start a deep session with a top-tier AI partner. Callio understands what you say and works quietly in the background: retrieving codebases, analyzing architecture, pulling data, running tests, generating documentation, and returning the right feedback at the right time.

Callio is not a passive Q and A tool. It is an active collaborator. During your conversation, it keeps context, anticipates needs, and proactively suggests better paths. When discussion ends, it can compile a TODO list, wait for your confirmation, execute tasks directly, and report outcomes so the conversation can continue without breaking flow.

Our vision is simple: give everyone a super-intelligent agent that is always online, deeply informed, and proactive. Not a cold chatbot, but a real digital partner that understands you, assists you, and co-creates with you. Callio is open source and self-hostable, so your data, code, and conversations stay under your control.

This is not Siri. This is not Alexa. This is Callio.

## Why Callio

- Voice-first, full-duplex interaction over WebSocket
- Session-aware planning and async task execution
- Multi-client access in one workspace: Web, Mobile, and CLI
- Pluggable STT, TTS, LLM, and agent backends
- Proactive collaboration with resumable conversations

## Use Cases

### 1. Voice-Driven Code Review and Optimization

Scenario: You are driving home and remember an API in `order-service` may become slow with larger data volume.

You call Callio and ask it to inspect the endpoint. Callio pulls the latest code, analyzes SQL and index usage, then reports that the query is missing the composite index on `user_id` and `created_at`, causing full-table scans. It offers to generate the migration script immediately.

You confirm, and by the time you are home, the migration is ready in a pull request.

### 2. Architecture Discussion and Feature Iteration

Scenario: You are evaluating RabbitMQ vs Kafka for async notifications.

Callio analyzes your current architecture and traffic pattern, explains why RabbitMQ fits your scale better today, flags operational factors on Kubernetes, and offers a concrete rollout plan.

After the discussion, Callio generates a task list, then executes confirmed items: Helm manifests, deployment docs, and CI/CD updates. It notifies you when the PR is ready.

### 3. Real-Time Bug Localization and Collaborative Debugging

Scenario: Production memory usage keeps growing and you need immediate diagnosis.

Callio fetches monitoring context and logs, identifies suspicious components, pinpoints the likely regression window, and proposes rollback or code-level fixes. You keep discussing by voice while Callio validates hypotheses.

After fix confirmation, it runs tests and prepares the patch for review.

### 4. Project Onboarding and Knowledge Transfer

Scenario: A new teammate joins and needs fast architecture onboarding.

Callio scans the codebase, maps module boundaries and data flow, and produces a structured onboarding brief plus a short walkthrough script. New members can listen first, then read documentation, reducing onboarding friction.

## Architecture Overview

Core modules:

- `callio/config`: runtime settings and environment configuration
- `callio/core`: FastAPI APIs, SQLite state, memory hub
- `callio/voice`: voice pipeline and audio backend integrations
- `callio/worker`: task dispatch, agent resolution, sandbox runner scaffolding
- `callio/meta`: rollout and sanity-check scaffolding
- `app/web`, `app/mobile`, `app/cli`, `app/shared`: user-facing clients

## Feature Matrix

- Voice-first interaction with server-side STT/TTS orchestration
- Web, mobile, and CLI clients with shared frontend assets
- Background task orchestration with progress tracking and logs
- Session resume support for continuous conversations
- Pluggable STT backends (`whisper`, `sensevoice`)
- Pluggable TTS backends (`chatt`, `say`, `edge`, `cosyvoice`, `fish`)
- Pluggable agent backends (`hermes`, `openclaw`, `goose`, `aider`, `claude`)
- Pluggable LLM providers (`ollama`, `openai`, `anthropic`, `gemini`, `openai_compatible`)

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

Use Python from `venv` to avoid incompatible dependency resolution from system or conda environments.

## Usage

### Service Startup

```bash
./venv/bin/python -m callio
```

Optional startup flag:

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
| `CALLIO_LLM_API_KEY` | _(empty)_ | API key for selected provider (falls back to `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) |
| `CALLIO_LLM_BASE_URL` | _(empty)_ | Base URL override for `openai_compatible` or provider proxy routing |
| `CALLIO_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama endpoint when `CALLIO_LLM_PROVIDER=ollama` |
| `CALLIO_NOTIFY_WECHAT_WEBHOOK` | _(empty)_ | WeChat webhook for end-of-session summary notifications |
| `CALLIO_NOTIFY_FEISHU_WEBHOOK` | _(empty)_ | Feishu webhook for end-of-session summary notifications |
| `CALLIO_NOTIFY_DISCORD_WEBHOOK` | _(empty)_ | Discord webhook for end-of-session summary notifications |
| `CALLIO_NOTIFY_TELEGRAM_WEBHOOK` | _(empty)_ | Telegram webhook for end-of-session summary notifications |
| `CALLIO_NOTIFY_TIMEOUT_SEC` | `8` | Timeout in seconds for notification webhook requests |
| `CALLIO_PORT` | `8000` | Service port |
| `CALLIO_HOST` | `0.0.0.0` | Service bind host |
| `CALLIO_APP_DIR` | `./app` | Top-level client workspace |

See all options in `callio/config/settings.py`.

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

## Join the Journey

Callio is under active development. We believe voice is the most natural interface between humans and machines, and LLMs make truly intelligent conversation possible.

Star, fork, and contribute. Build the personal AI partner everyone deserves.

Repository: https://github.com/dirtydog996/Callio

## Co-Builders Wanted

We are actively looking for open-source co-builders to shape Callio together.

- Product thinkers who care about voice-first AI experience
- Python and backend engineers (FastAPI, async task systems, orchestration)
- Speech engineers (STT/TTS pipeline optimization)
- Frontend engineers (Web and mobile voice interaction UX)
- DevOps and infra contributors (self-hosting, deployment, observability)
- Technical writers and community maintainers

If you want to build a truly proactive AI partner in the open, open an issue with your background and ideas, or submit a PR directly.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
