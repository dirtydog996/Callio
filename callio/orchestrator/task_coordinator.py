from __future__ import annotations

import uuid
from typing import Any

from callio.config.settings import Settings
from callio.core.database import Database
from callio.orchestrator.event_bus import EventBus
from callio.worker.kinds import TaskKind


class TaskCoordinator:
    def __init__(
        self,
        database: Database,
        event_bus: EventBus,
        task_dispatcher: Any,
        settings: Settings,
    ) -> None:
        self.database = database
        self.event_bus = event_bus
        self.task_dispatcher = task_dispatcher
        self.settings = settings

    async def confirm(
        self,
        session_id: str,
        node_ids: list[str] | None = None,
        *,
        confirm_all: bool = False,
    ) -> dict[str, Any]:
        if confirm_all:
            node_ids = [
                str(n["node_id"])
                for n in self.database.list_spec_nodes(session_id=session_id)
                if n.get("phase") == "PROPOSED"
            ]
        node_ids = node_ids or []

        running = self.database.count_running_tasks(session_id)
        confirmed: list[str] = []

        for node_id in node_ids:
            if running + len(confirmed) >= self.settings.max_parallel_tasks:
                break
            if self.database.count_running_tasks_global() >= self.settings.global_max_parallel:
                break
            node = self.database.get_spec_node(node_id)
            if not node or node.get("session_id") != session_id:
                continue
            if node.get("phase") != "PROPOSED":
                continue

            kind = str(node.get("kind") or TaskKind.EXECUTE.value)
            self.database.update_spec_status(node_id, "PENDING", phase="CONFIRMED")
            confirmed.append(node_id)

            await self.event_bus.emit(
                session_id,
                "TASK_CONFIRMED",
                {"node_id": node_id, "title": node.get("feature_name"), "kind": kind},
            )
            await self.task_dispatcher.dispatch({
                "node_id": node_id,
                "session_id": session_id,
                "feature_name": node.get("feature_name"),
                "description": node.get("description"),
                "kind": kind,
            })
            running += 1

        if not confirmed:
            return {"confirmed": [], "message": "没有可确认的任务，或已达并行上限。"}
        return {
            "confirmed": confirmed,
            "message": f"已确认并派发 {len(confirmed)} 项后台任务，通话可继续。",
            "speak_hint": "好的，已在后台开始执行。" if confirmed else "没有任务被确认。",
        }

    async def dispatch_background_summary(self, session_id: str, transcript: str) -> None:
        node_id = str(uuid.uuid4())
        self.database.upsert_spec_node(
            node_id,
            "会话摘要",
            transcript,
            session_id=session_id,
            kind=TaskKind.SUMMARIZE.value,
            phase="CONFIRMED",
            status="PENDING",
        )
        await self.task_dispatcher.dispatch({
            "node_id": node_id,
            "session_id": session_id,
            "feature_name": "会话摘要",
            "description": transcript,
            "kind": TaskKind.SUMMARIZE.value,
        })

    async def finalize_summary(self, session_id: str, transcript: str) -> None:
        if not transcript.strip():
            return
        await self.dispatch_background_summary(session_id, transcript)
