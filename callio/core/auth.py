"""API token auth: verification helpers + ASGI middleware covering HTTP and WebSocket."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any
from urllib.parse import parse_qs

from fastapi.responses import JSONResponse

PUBLIC_PATHS = {"/api/v1/health"}
WS_PATHS = {"/ws", "/ws/status"}


def generate_token() -> str:
    return "cio_" + secrets.token_hex(20)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_token(database: Any, token: str | None, bootstrap_token: str) -> bool:
    if not token:
        return False
    if bootstrap_token and hmac.compare_digest(token, bootstrap_token):
        return True
    token_hash = hash_token(token)
    row = database.get_api_token(token_hash)
    if row is None:
        return False
    database.touch_api_token(token_hash)
    return True


def _extract_token(scope: dict) -> str | None:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # WS clients (iOS URLSessionWebSocketTask) cannot set headers; also handy for curl
    query = parse_qs(scope.get("query_string", b"").decode())
    return (query.get("token") or [None])[0]


class AuthMiddleware:
    """Bare ASGI middleware (not BaseHTTPMiddleware, which breaks websockets)."""

    def __init__(self, app: Any, auth_enabled: bool, database: Any, bootstrap_token: str = "") -> None:
        self.app = app
        self.auth_enabled = auth_enabled  # snapshot at startup; toggle requires restart
        self.database = database
        self.bootstrap_token = bootstrap_token

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if not self.auth_enabled or scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        needs_auth = (
            scope["type"] == "http" and path.startswith("/api/v1/") and path not in PUBLIC_PATHS
        ) or (scope["type"] == "websocket" and path in WS_PATHS)
        if not needs_auth or check_token(self.database, _extract_token(scope), self.bootstrap_token):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http":
            await JSONResponse({"detail": "unauthorized"}, status_code=401)(scope, receive, send)
        else:
            # close before accept; uvicorn turns this into a handshake 403
            await send({"type": "websocket.close", "code": 4401, "reason": "unauthorized"})
