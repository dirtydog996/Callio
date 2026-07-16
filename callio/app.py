from __future__ import annotations

import sys
from typing import Sequence

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional at runtime
    def load_dotenv(*args, **kwargs):
        return False

from fastapi import FastAPI

load_dotenv()

from callio.config.settings import Settings, get_settings
from callio.core.server import create_app
from callio.logging_config import configure_logging
from callio.voice.pipeline import register_voice_routes
from callio.web import MOBILE_CLIENT_PATH, WEB_CLIENT_PATH


def create_runtime_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or get_settings()
    app = create_app(runtime_settings)
    register_voice_routes(app, runtime_settings)
    return app


settings = get_settings()
app = create_runtime_app(settings)


def _local_ip() -> str:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _client_base_url(settings: Settings) -> str:
    scheme = "https" if settings.ssl_certfile and settings.ssl_keyfile else "http"
    return f"{scheme}://{_local_ip()}:{settings.port}"


def show_local_qr(settings: Settings | None = None) -> None:
    import qrcode

    runtime_settings = settings or get_settings()
    base_url = _client_base_url(runtime_settings)
    web_url = f"{base_url}{WEB_CLIENT_PATH}"
    mobile_url = f"{base_url}{MOBILE_CLIENT_PATH}"
    print("\n=======================================================")
    print("🏠 Callio is ready!")
    print(f"🖥️  Web client: {web_url}")
    print(f"📱 Mobile client: {mobile_url}")
    if runtime_settings.ssl_certfile and runtime_settings.ssl_keyfile:
        print("🔒 HTTPS enabled — microphone works on mobile")
    else:
        print("⚠️  HTTP mode — iPhone usually cannot use microphone via QR code")
        print("   Configure CALLIO_SSL_CERT / CALLIO_SSL_KEY to enable HTTPS")
    print("=======================================================")

    qr = qrcode.QRCode(version=1, border=1, box_size=1)
    qr.add_data(mobile_url)
    qr.make(fit=True)

    if sys.stdout.isatty():
        qr.print_tty()
    else:
        qr.print_ascii(invert=True)
    print()


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging()

    import uvicorn

    args = list(argv if argv is not None else sys.argv[1:])
    show_qr = "--no-qr" not in args and "worker" not in args
    if show_qr:
        show_local_qr(settings)
    ssl_kwargs = {}
    if settings.ssl_certfile and settings.ssl_keyfile:
        ssl_kwargs["ssl_certfile"] = settings.ssl_certfile
        ssl_kwargs["ssl_keyfile"] = settings.ssl_keyfile

    uvicorn.run(
        "callio.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        timeout_graceful_shutdown=3,
        **ssl_kwargs,
    )
