Call your PC, talk to your Agent, and let it handle the I/O.

Callio is a voice-first autonomous OS companion built around a modular Python service architecture:

- `callio/config` — runtime settings
- `callio/core` — FastAPI API, SQLite state, memory hub
- `callio/voice` — Pipecat voice pipeline and tool triggers
- `callio/worker` — async task dispatching, sandbox runner scaffolding
- `callio/meta` — shadow rollout and sanity-check scaffolding

## Run locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the integrated service:

```bash
python -m callio
```

This starts the FastAPI app, mounts the static web client, registers the voice websocket route, and shows a local QR code by default.

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
