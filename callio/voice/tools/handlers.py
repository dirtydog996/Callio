from __future__ import annotations

from typing import Any, Callable, Coroutine

from callio.orchestrator import Orchestrator


def create_tool_handlers(orchestrator: Orchestrator, session_id: str) -> dict[str, Callable[..., Coroutine[Any, Any, None]]]:
    async def propose_tasks(params) -> None:
        tasks = params.arguments.get("tasks", [])
        result = await orchestrator.proposals.propose(session_id, tasks)
        await params.result_callback(result)

    async def confirm_tasks(params) -> None:
        node_ids = params.arguments.get("node_ids", [])
        confirm_all = bool(params.arguments.get("confirm_all", False))
        result = await orchestrator.coordinator.confirm(
            session_id, node_ids, confirm_all=confirm_all,
        )
        await params.result_callback(result)

    async def cancel_proposal(params) -> None:
        node_ids = params.arguments.get("node_ids", [])
        result = await orchestrator.proposals.cancel(session_id, node_ids)
        await params.result_callback(result)

    async def get_session_progress(params) -> None:
        snap = orchestrator.progress.snapshot(session_id)
        snap["context_block"] = orchestrator.progress.build_context_block(session_id)
        await params.result_callback(snap)

    async def propose_summary(params) -> None:
        transcript = orchestrator.transcripts.get_transcript(session_id)
        focus = params.arguments.get("focus", "")
        if focus:
            transcript = f"Focus: {focus}\n{transcript}"
        await orchestrator.coordinator.dispatch_background_summary(session_id, transcript)
        await params.result_callback({
            "status": "scheduled",
            "message": "Summary and action plan generated in the background.",
        })

    return {
        "propose_tasks": propose_tasks,
        "confirm_tasks": confirm_tasks,
        "cancel_proposal": cancel_proposal,
        "get_session_progress": get_session_progress,
        "propose_summary": propose_summary,
    }
