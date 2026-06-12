from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from callio.config.settings import Settings, get_settings
from callio.web import WEB_CLIENT_PATH
from callio.core.database import Database
from callio.core.memory import MemoryHub
from callio.worker.tasks import TaskDispatcher


class TodoItem(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    feature_name: str
    description: str
    difficulty_level: int = 1


class SessionItem(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    transcript: str = ""
    summary: str = ""


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast_status(self, message: dict[str, Any]) -> None:
        stale_connections: list[WebSocket] = []
        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    stale_connections.append(connection)
            for connection in stale_connections:
                self.active_connections.discard(connection)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    Path(settings.static_dir).mkdir(parents=True, exist_ok=True)

    database = Database(settings)
    memory_hub = MemoryHub(database, settings)
    manager = ConnectionManager()
    task_dispatcher = TaskDispatcher(database, memory_hub, manager, settings)

    app = FastAPI(title=settings.app_title, version=settings.app_version)

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url=WEB_CLIENT_PATH)

    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
    app.state.settings = settings
    app.state.database = database
    app.state.memory_hub = memory_hub
    app.state.status_manager = manager
    app.state.task_dispatcher = task_dispatcher

    @app.on_event("startup")
    async def startup() -> None:
        database.initialize()

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        database.initialize()
        whisper_ready = False
        try:
            from callio.voice.whisper_loader import get_preload_error, is_whisper_ready

            whisper_ready = is_whisper_ready()
            whisper_error = get_preload_error()
        except Exception:
            whisper_error = None

        return {
            "status": "ok",
            "database": Path(settings.db_path).exists(),
            "voice_enabled": True,
            "whisper_ready": whisper_ready,
            "whisper_error": whisper_error,
            "queue_backend": task_dispatcher.backend_name,
        }

    @app.get("/api/v1/tasks")
    async def list_tasks() -> dict[str, Any]:
        return {"items": database.list_spec_nodes()}

    @app.get("/api/v1/sessions")
    async def list_sessions() -> dict[str, Any]:
        return {"items": database.list_sessions()}

    @app.post("/api/v1/sessions")
    async def create_session(session: SessionItem) -> dict[str, str]:
        memory_hub.store_episode(session.session_id, session.title, session.transcript, session.summary)
        await manager.broadcast_status({
            "event": "SESSION_STORED",
            "session_id": session.session_id,
            "title": session.title,
        })
        return {"status": "stored", "session_id": session.session_id}

    @app.websocket("/ws/status")
    async def websocket_status(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        await websocket.send_json({
            "event": "SNAPSHOT",
            "tasks": database.list_spec_nodes(),
            "sessions": database.list_sessions(),
        })
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_json({"status": "heartbeat", "received": data})
        except WebSocketDisconnect:
            await manager.disconnect(websocket)

    @app.post("/api/v1/tasks/dispatch")
    async def dispatch_task(todo: TodoItem) -> dict[str, str]:
        database.upsert_spec_node(
            todo.node_id,
            todo.feature_name,
            todo.description,
            session_id=todo.session_id,
            difficulty_level=todo.difficulty_level,
            status="PENDING",
        )
        await manager.broadcast_status({
            "event": "TASK_DISPATCHED",
            "node_id": todo.node_id,
            "feature_name": todo.feature_name,
            "status": "PENDING",
        })
        await task_dispatcher.dispatch(todo.model_dump())
        return {"status": "dispatched", "node_id": todo.node_id}

    return app
