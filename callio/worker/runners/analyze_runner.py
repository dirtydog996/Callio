from __future__ import annotations

from typing import Awaitable, Callable

from callio.config.settings import Settings, get_settings
from callio.core.database import Database
from callio.core.task_log import TaskLog
from callio.llm.factory import build_chat_client
from callio.worker.repo_context import collect_repo_context

ProgressCallback = Callable[[dict[str, object]], Awaitable[None]]


class AnalyzeRunner:
    def __init__(self, database: Database, settings: Settings | None = None) -> None:
        self.database = database
        self.settings = settings or get_settings()
        self.task_log = TaskLog(database)
        self._client = build_chat_client(self.settings)

    async def run(
        self,
        node_id: str,
        session_id: str,
        description: str,
        progress_callback: ProgressCallback,
    ) -> None:
        run_id = self.task_log.start_run(node_id, session_id, "ANALYZE")
        self.database.update_spec_status(node_id, "RUNNING", phase="RUNNING")
        await progress_callback({
            "event": "TASK_RUNNING",
            "node_id": node_id,
            "session_id": session_id,
            "status": "RUNNING",
            "kind": "ANALYZE",
            "progress": 10,
        })

        repo_ctx = collect_repo_context(description, self.settings)
        prompt = (
            "You are a Callio analysis assistant. Using the repository context below, provide a concise Markdown report (max 400 words) for the requirement.\n\n"
            f"[Requirement]\n{description}\n\n"
            f"[Repository Context]\n{repo_ctx}"
        )

        try:
            response = await self._client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            report = (response.choices[0].message.content or "").strip()
            self.task_log.append_stdout(run_id, report, progress_pct=100)

            # Extract a concise result summary (first two sentences, max 300 chars).
            sentences = [s.strip() for s in report.replace("\n", " ").split(".") if s.strip()]
            brief = ". ".join(sentences[:2])
            if brief and not brief.endswith("."):
                brief += "."
            result_summary = brief[:300] if brief else report[:300]
            self.database.set_node_result_summary(node_id, result_summary)

            self.database.update_spec_status(node_id, "SUCCESS", phase="SUCCESS")
            self.task_log.finish_run(run_id, "SUCCESS")
            await progress_callback({
                "event": "TASK_COMPLETED",
                "node_id": node_id,
                "session_id": session_id,
                "status": "SUCCESS",
                "kind": "ANALYZE",
                "report": report[:500],
                "result_summary": result_summary,
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
