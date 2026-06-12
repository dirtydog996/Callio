from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import uvicorn

from callio.config.settings import get_settings
from callio.core.server import create_app
from callio.voice.pipeline import register_voice_routes


settings = get_settings()
app = create_app(settings)
register_voice_routes(app, settings)


def show_local_qr() -> None:
    import socket

    import qrcode

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = "127.0.0.1"
    finally:
        s.close()

    index_path = Path(settings.static_dir).joinpath("index.html")
    local_url = f"http://{local_ip}:8000/static/{index_path.name}"
    print("\n=======================================================")
    print("🏠 Callio 服务已启动！")
    print(f"🔗 局域网 Web 调试端链接: {local_url}")
    print("=======================================================")

    qr = qrcode.QRCode(version=1, box_size=5, border=1)
    qr.add_data(local_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        img.save(tmp.name)
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, tmp.name], check=False)


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] != "worker":
        show_local_qr()
    uvicorn.run("local:app", host="0.0.0.0", port=8000, reload=False)
