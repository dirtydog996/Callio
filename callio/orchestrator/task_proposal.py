from __future__ import annotations

import uuid
from typing import Any

from callio.core.database import Database
from callio.orchestrator.event_bus import EventBus
from callio.worker.kinds import TaskKind


class TaskProposal:
    def __init__(self, database: Database, event_bus: EventBus) -> None:
        self.database = database
        self.event_bus = event_bus

    async def propose(
        self,
        session_id: str,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        created: list[dict[str, str]] = []
        preview_lines: list[str] = []

        for index, item in enumerate(tasks, start=1):
            title = str(item.get("title", "")).strip() or f"任务{index}"
            description = str(item.get("description", "")).strip()
            kind = str(item.get("kind", TaskKind.EXECUTE.value)).upper()
            if kind not in {k.value for k in TaskKind}:
                kind = TaskKind.EXECUTE.value

            actions = [str(a) for a in (item.get("actions") or []) if str(a).strip()]

            node_id = str(uuid.uuid4())
            self.database.upsert_spec_node(
                node_id, title, description,
                session_id=session_id, kind=kind, phase="PROPOSED", status="DRAFT",
            )
            created.append({"node_id": node_id, "title": title, "kind": kind})
            action_hint = f"（{len(actions)} 项行动）" if actions else ""
            preview_lines.append(f"{index}. [{kind}] {title}{action_hint}：{description}")

            await self.event_bus.emit(session_id, "TASK_PROPOSED", {
                "node_id": node_id, "title": title, "kind": kind,
                "description": description, "actions": actions,
            })

        preview_text = "\n".join(preview_lines)
        return {
            "tasks": created,
            "preview_text": preview_text,
            "message": f"已提议 {len(created)} 项任务，请向用户朗读并等待确认。",
        }

    async def cancel(self, session_id: str, node_ids: list[str]) -> dict[str, Any]:
        cancelled: list[str] = []
        for node_id in node_ids:
            node = self.database.get_spec_node(node_id)
            if not node or node.get("session_id") != session_id:
                continue
            if node.get("phase") != "PROPOSED":
                continue
            self.database.update_spec_status(node_id, "CANCELLED", phase="CANCELLED")
            cancelled.append(node_id)
            await self.event_bus.emit(session_id, "TASK_CANCELLED", {"node_id": node_id})
        return {"cancelled": cancelled, "message": f"已取消 {len(cancelled)} 项未确认任务。"}
