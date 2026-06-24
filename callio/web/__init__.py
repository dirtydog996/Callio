from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
APP_DIR = PROJECT_ROOT / "app"
WEB_DIR = APP_DIR / "web"
MOBILE_DIR = APP_DIR / "mobile"
SHARED_DIR = APP_DIR / "shared"
STATIC_DIR = WEB_DIR
WEB_CLIENT_PATH = "/app/web/index.html"
MOBILE_CLIENT_PATH = "/app/mobile/index.html"
