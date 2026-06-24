from __future__ import annotations

import json
from typing import Awaitable, Callable

from callio.config.settings import Settings, get_settings
from callio.core.database import Database
from callio.core.memory import MemoryHub
from callio.core.task_log import TaskLog
from callio.llm.factory import build_chat_client
from callio.worker.repo_context import collect_repo_context

ProgressCallback = Callable[[dict[str, object]], Awaitable[None]]


class SummarizeRunner:
    def __init__(
        self,
        database: Database,
        memory_hub: MemoryHub | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.database = database
        self.memory_hub = memory_hub
        self.settings = settings or get_settings()
        self.task_log = TaskLog(database)
        self._client = build_chat_client(self.settings)

    async def run(
        self,
        node_id: str,
        session_id: str,
        transcript: str,
        progress_callback: ProgressCallback,
    ) -> None:
        run_id = self.task_log.start_run(node_id, session_id, "SUMMARIZE")
        self.database.update_spec_status(node_id, "RUNNING", phase="RUNNING")
        await progress_callback({
            "event": "TASK_RUNNING",
            "node_id": node_id,
            "session_id": session_id,
            "status": "RUNNING",
            "kind": "SUMMARIZE",
            "progress": 10,
        })

        prompt = (
            "你是 Callio 会话助手。根据以下通话转写，输出 JSON："
            '{"summary":"一两句话摘要","action_plan":"Markdown 行动计划列表"}。'
            "只输出 JSON，不要其他文字。\n\n"
            f"{transcript}"
        )

        try:
            response = await self._client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            content = (response.choices[0].message.content or "").strip()
            self.task_log.append_stdout(run_id, content[:500])
            summary = content
            action_plan = ""
            try:
                parsed = json.loads(content)
                summary = str(parsed.get("summary", content))
                action_plan = str(parsed.get("action_plan", ""))
            except json.JSONDecodeError:
                pass

            self.database.update_session(session_id, summary=summary, action_plan=action_plan)
            if self.memory_hub and summary:
                session = self.database.get_session(session_id) or {}
                self.memory_hub.add_semantic_memory(
                    document_id=f"{session_id}:summary",
                    content=summary,
                    metadata={"kind": "summary", "title": str(session.get("title", ""))},
                )

            self.database.update_spec_status(node_id, "SUCCESS", phase="SUCCESS")
            self.task_log.finish_run(run_id, "SUCCESS")
            await progress_callback({
                "event": "SUMMARY_UPDATED",
                "node_id": node_id,
                "session_id": session_id,
                "status": "SUCCESS",
                "summary": summary,
                "progress": 100,
            })
            await progress_callback({
                "event": "TASK_COMPLETED",
                "node_id": node_id,
                "session_id": session_id,
                "status": "SUCCESS",
                "progress": 100,
            })
        except Exception as exc:
            error = str(exc)
            self.database.update_spec_status(node_id, "FAILED", error, phase="FAILED")
            self.task_log.append_stdout(run_id, error)
            self.task_log.finish_run(run_id, "FAILED")
            await progress_callback({
                "event": "TASK_COMPLETED",
                "node_id": node_id,
                "session_id": session_id,
                "status": "FAILED",
                "error": error,
                "progress": 100,
            })
