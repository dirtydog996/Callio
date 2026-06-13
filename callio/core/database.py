from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
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
                    action_plan TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS spec_nodes (
                    node_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(session_id),
                    feature_name TEXT NOT NULL,
                    description TEXT,
                    kind TEXT DEFAULT 'EXECUTE',
                    phase TEXT DEFAULT 'PROPOSED',
                    difficulty_level INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'DRAFT',
                    error_log TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS task_runs (
                    run_id TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT DEFAULT 'RUNNING',
                    stdout_tail TEXT,
                    progress_pct INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS session_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    claimed_at TIMESTAMP
                );
                """
            )
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        session_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "action_plan" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN action_plan TEXT")
        if "ended_at" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN ended_at TIMESTAMP")

        node_cols = {row[1] for row in conn.execute("PRAGMA table_info(spec_nodes)").fetchall()}
        if "kind" not in node_cols:
            conn.execute("ALTER TABLE spec_nodes ADD COLUMN kind TEXT DEFAULT 'EXECUTE'")
        if "phase" not in node_cols:
            conn.execute("ALTER TABLE spec_nodes ADD COLUMN phase TEXT DEFAULT 'PROPOSED'")

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
        kind: str = "EXECUTE",
        phase: str = "PROPOSED",
        difficulty_level: int = 1,
        status: str = "DRAFT",
        error_log: str | None = None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO spec_nodes (
                    node_id, session_id, feature_name, description, kind, phase,
                    difficulty_level, status, error_log
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    feature_name=excluded.feature_name,
                    description=excluded.description,
                    kind=excluded.kind,
                    phase=excluded.phase,
                    difficulty_level=excluded.difficulty_level,
                    status=excluded.status,
                    error_log=excluded.error_log,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (node_id, session_id, feature_name, description, kind, phase, difficulty_level, status, error_log),
            )
            conn.commit()

    def create_session(
        self,
        session_id: str,
        title: str,
        transcript: str = "",
        summary: str = "",
        *,
        action_plan: str = "",
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, title, transcript, summary, action_plan)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    title=excluded.title,
                    transcript=excluded.transcript,
                    summary=excluded.summary,
                    action_plan=excluded.action_plan
                """,
                (session_id, title, transcript, summary, action_plan),
            )
            conn.commit()

    def update_session(
        self,
        session_id: str,
        *,
        transcript: str | None = None,
        summary: str | None = None,
        action_plan: str | None = None,
        ended_at: str | None = None,
        clear_ended_at: bool = False,
    ) -> None:
        fields: list[str] = []
        values: list[object] = []
        if transcript is not None:
            fields.append("transcript = ?")
            values.append(transcript)
        if summary is not None:
            fields.append("summary = ?")
            values.append(summary)
        if action_plan is not None:
            fields.append("action_plan = ?")
            values.append(action_plan)
        if ended_at is not None:
            fields.append("ended_at = ?")
            values.append(ended_at)
        if clear_ended_at:
            fields.append("ended_at = NULL")
        if not fields:
            return
        values.append(session_id)
        with self.connection() as conn:
            conn.execute(f"UPDATE sessions SET {', '.join(fields)} WHERE session_id = ?", values)
            conn.commit()

    def get_session(self, session_id: str) -> dict[str, object] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT session_id, title, transcript, summary, action_plan, created_at, ended_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_spec_status(
        self,
        node_id: str,
        status: str,
        error_log: str | None = None,
        *,
        phase: str | None = None,
    ) -> None:
        with self.connection() as conn:
            if phase is not None:
                conn.execute(
                    """
                    UPDATE spec_nodes
                    SET status = ?, phase = ?, error_log = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE node_id = ?
                    """,
                    (status, phase, error_log, node_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE spec_nodes
                    SET status = ?, error_log = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE node_id = ?
                    """,
                    (status, error_log, node_id),
                )
            conn.commit()

    def get_spec_node(self, node_id: str) -> dict[str, object] | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT node_id, session_id, feature_name, description, kind, phase,
                       difficulty_level, status, error_log, updated_at
                FROM spec_nodes WHERE node_id = ?
                """,
                (node_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_spec_nodes(self, *, session_id: str | None = None) -> list[dict[str, object]]:
        with self.connection() as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT node_id, session_id, feature_name, description, kind, phase,
                           difficulty_level, status, error_log, updated_at
                    FROM spec_nodes
                    WHERE session_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT node_id, session_id, feature_name, description, kind, phase,
                           difficulty_level, status, error_log, updated_at
                    FROM spec_nodes
                    ORDER BY updated_at DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]

    def count_running_tasks(self, session_id: str) -> int:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM spec_nodes
                WHERE session_id = ? AND status = 'RUNNING'
                """,
                (session_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def list_sessions(self) -> list[dict[str, object]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, transcript, summary, action_plan, created_at, ended_at
                FROM sessions
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_session_event(self, event_id: str, session_id: str, kind: str, payload: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO session_events (event_id, session_id, kind, payload)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, session_id, kind, payload),
            )
            conn.commit()

    def list_session_events(self, session_id: str, *, limit: int = 100) -> list[dict[str, object]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT event_id, session_id, kind, payload, created_at
                FROM session_events
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_task_run(self, run_id: str, node_id: str, session_id: str, kind: str, *, status: str = "RUNNING") -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO task_runs (run_id, node_id, session_id, kind, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, node_id, session_id, kind, status),
            )
            conn.commit()

    def append_task_run_stdout(
        self,
        run_id: str,
        line: str,
        *,
        progress_pct: int | None = None,
        tail_limit: int = 8000,
    ) -> None:
        with self.connection() as conn:
            row = conn.execute("SELECT stdout_tail FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return
            current = row["stdout_tail"] or ""
            merged = (current + line)[-tail_limit:]
            if progress_pct is not None:
                conn.execute(
                    "UPDATE task_runs SET stdout_tail = ?, progress_pct = ? WHERE run_id = ?",
                    (merged, progress_pct, run_id),
                )
            else:
                conn.execute("UPDATE task_runs SET stdout_tail = ? WHERE run_id = ?", (merged, run_id))
            conn.commit()

    def finish_task_run(self, run_id: str, status: str) -> None:
        finished = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                "UPDATE task_runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (status, finished, run_id),
            )
            conn.commit()

    def list_task_runs(self, *, session_id: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        with self.connection() as conn:
            if session_id:
                rows = conn.execute(
                    """
                    SELECT run_id, node_id, session_id, kind, status, stdout_tail,
                           progress_pct, started_at, finished_at
                    FROM task_runs
                    WHERE session_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT run_id, node_id, session_id, kind, status, stdout_tail,
                           progress_pct, started_at, finished_at
                    FROM task_runs
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def count_running_tasks_global(self) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM spec_nodes WHERE status = 'RUNNING'"
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def list_task_runs_for_node(self, node_id: str) -> list[dict[str, object]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT run_id, node_id, session_id, kind, status, stdout_tail,
                       progress_pct, started_at, finished_at
                FROM task_runs WHERE node_id = ?
                ORDER BY started_at DESC
                """,
                (node_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def enqueue_task(self, payload: str) -> int:
        import json as _json

        data = _json.loads(payload)
        node_id = str(data.get("node_id", ""))
        with self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO task_queue (node_id, payload, status) VALUES (?, ?, 'PENDING')",
                (node_id, payload),
            )
            conn.commit()
            return int(cur.lastrowid)

    def count_queued_tasks(self, status: str = "PENDING") -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM task_queue WHERE status = ?",
                (status,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def claim_next_task(self) -> tuple[int, dict[str, object]] | None:
        import json as _json

        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT id, payload FROM task_queue
                WHERE status = 'PENDING'
                ORDER BY id ASC LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            queue_id = int(row["id"])
            conn.execute(
                """
                UPDATE task_queue SET status = 'CLAIMED', claimed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (queue_id,),
            )
            conn.commit()
        return queue_id, _json.loads(row["payload"])

    def complete_task(self, queue_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE task_queue SET status = ? WHERE id = ?", (status, queue_id))
            conn.commit()

    def reset_claimed_tasks(self) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                "UPDATE task_queue SET status = 'PENDING', claimed_at = NULL WHERE status = 'CLAIMED'"
            )
            conn.commit()
            return cur.rowcount

    def cancel_queued_for_node(self, node_id: str) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE task_queue
                SET status = 'CANCELLED'
                WHERE node_id = ? AND status IN ('PENDING', 'CLAIMED')
                """,
                (node_id,),
            )
            conn.commit()
            return cur.rowcount
