from __future__ import annotations

import sys
from typing import Sequence

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from callio.config.settings import Settings, get_settings
from callio.core.server import create_app
from callio.voice.pipeline import register_voice_routes
from callio.web import WEB_CLIENT_PATH


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
    local_url = f"{_client_base_url(runtime_settings)}{WEB_CLIENT_PATH}"
    print("\n=======================================================")
    print("🏠 Callio 服务已启动！")
    print(f"🔗 局域网 Web 调试端链接: {local_url}")
    if runtime_settings.ssl_certfile and runtime_settings.ssl_keyfile:
        print("🔒 已启用 HTTPS，手机端可使用麦克风")
    else:
        print("⚠️  当前为 HTTP，iPhone 扫码后通常无法使用麦克风")
        print("   请配置 CALLIO_SSL_CERT / CALLIO_SSL_KEY 启用 HTTPS")
    print("=======================================================")

    qr = qrcode.QRCode(version=1, border=1, box_size=1)
    qr.add_data(local_url)
    qr.make(fit=True)

    if sys.stdout.isatty():
        qr.print_tty()
    else:
        qr.print_ascii(invert=True)
    print()


def main(argv: Sequence[str] | None = None) -> None:
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
