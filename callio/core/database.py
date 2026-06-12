from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from callio.config.settings import Settings, get_settings


class Database:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = Path(self.settings.db_path)
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    transcript TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS spec_nodes (
                    node_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(session_id),
                    feature_name TEXT NOT NULL,
                    description TEXT,
                    difficulty_level INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'DRAFT',
                    error_log TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def upsert_spec_node(
        self,
        node_id: str,
        feature_name: str,
        description: str,
        *,
        session_id: str | None = None,
        difficulty_level: int = 1,
        status: str = "PENDING",
        error_log: str | None = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO spec_nodes (node_id, session_id, feature_name, description, difficulty_level, status, error_log)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    feature_name=excluded.feature_name,
                    description=excluded.description,
                    difficulty_level=excluded.difficulty_level,
                    status=excluded.status,
                    error_log=excluded.error_log,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (node_id, session_id, feature_name, description, difficulty_level, status, error_log),
            )
            conn.commit()

    def create_session(self, session_id: str, title: str, transcript: str = "", summary: str = "") -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, title, transcript, summary)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    title=excluded.title,
                    transcript=excluded.transcript,
                    summary=excluded.summary
                """,
                (session_id, title, transcript, summary),
            )
            conn.commit()

    def update_spec_status(self, node_id: str, status: str, error_log: str | None = None) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE spec_nodes
                SET status = ?, error_log = ?, updated_at = CURRENT_TIMESTAMP
                WHERE node_id = ?
                """,
                (status, error_log, node_id),
            )
            conn.commit()

    def list_spec_nodes(self) -> list[dict[str, object]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT node_id, session_id, feature_name, description, difficulty_level, status, error_log, updated_at
                FROM spec_nodes
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_sessions(self) -> list[dict[str, object]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, transcript, summary, created_at
                FROM sessions
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]
