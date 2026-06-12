Call your PC, talk to your Agent, and let it handle the I/O.

Callio is a voice-first autonomous OS companion built around a modular Python service architecture:

- `callio/config` — runtime settings
- `callio/core` — FastAPI API, SQLite state, memory hub
- `callio/web` — browser voice client (`static/index.html`)
- `callio/voice` — Pipecat voice pipeline and tool triggers
- `callio/worker` — async task dispatching, sandbox runner scaffolding
- `callio/meta` — shadow rollout and sanity-check scaffolding

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CALLIO_HF_ENDPOINT` | _(empty)_ | Hugging Face mirror, e.g. `https://hf-mirror.com` for faster model downloads in China |
| `CALLIO_WHISPER_MODEL` | `base` | Whisper model size (`base`, `small`, `medium`, etc.) |
| `CALLIO_WHISPER_PRELOAD` | `1` | Preload Whisper at startup instead of on first WebSocket connection |
| `CALLIO_SSL_CERT` | _(empty)_ | HTTPS certificate path (required for mobile microphone) |
| `CALLIO_SSL_KEY` | _(empty)_ | HTTPS private key path |
| `CALLIO_PORT` | `8000` | Server port |

Whisper models are cached under `~/.cache/huggingface/hub/`. After the first download, startup only loads from the local cache.

## Mobile testing (iPhone / Android)

手机通过局域网 HTTP 扫码无法使用麦克风，需 HTTPS。一键启动：

```bash
./scripts/start-mobile-https.sh
```

完整说明见 **[docs/mobile-testing.md](docs/mobile-testing.md)**（mkcert / ngrok、iPhone 证书信任、常见问题）。全双工语音架构见 **[docs/voice-full-duplex.md](docs/voice-full-duplex.md)**。

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the integrated service:

```bash
python -m callio
```

This starts the FastAPI app, serves the web client at `/` and `/static/index.html`, registers the voice websocket route, and prints a small QR code in the terminal by default.

If you want to skip QR display:

```bash
python -m callio --no-qr
```

You can also serve the ASGI app directly:

```bash
uvicorn callio.app:app --host 0.0.0.0 --port 8000
```

## Main endpoints

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks/dispatch`
- `GET /api/v1/sessions`
- `POST /api/v1/sessions`
- `WS /ws/status`
- `WS /ws`

## Validation

Basic validation used in this repository today:

```bash
python -m compileall callio
python - <<'PY'
from callio.app import app
print(len(app.routes))
PY
```

export HF_ENDPOINT=https://hf-mirror.com

export CALLIO_HF_ENDPOINT=https://hf-mirror.com