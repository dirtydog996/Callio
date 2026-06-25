from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from callio.config.settings import Settings
from callio.voice.memory_context import build_memory_block
from callio.voice.prompt import build_system_prompt
from callio.voice.resume_context import build_resume_block

if TYPE_CHECKING:
    from callio.orchestrator import Orchestrator
    from pipecat.processors.aggregators.llm_context import LLMContext


def _build_prompt(
    orchestrator: Orchestrator,
    session_id: str,
    settings: Settings,
    memory_hub,
) -> str:
    """Gather context from DB/memory and build the full system prompt string.

    This is designed to be called from a thread pool executor so that
    synchronous DB and vector-search I/O does not block the event loop.
    """
    progress_block = ""
    memory_block = ""
    if settings.progress_inject:
        progress_block = orchestrator.progress.build_context_block(session_id)
    if settings.memory_inject and memory_hub is not None:
        memory_block = build_memory_block(memory_hub, orchestrator.database)
    resume_block = build_resume_block(orchestrator.database, session_id)
    return build_system_prompt(
        settings.voice_response_limit,
        progress_block=progress_block,
        memory_block=memory_block,
        resume_block=resume_block,
    )


def _apply_prompt(context: LLMContext, prompt: str) -> None:
    """Patch the system message in-place on the event-loop thread."""
    messages = context.messages
    if not messages:
        context.messages = [{"role": "system", "content": prompt}]
        return
    if messages[0].get("role") == "system":
        messages[0]["content"] = prompt
    else:
        messages.insert(0, {"role": "system", "content": prompt})


async def refresh_system_prompt(
    context: LLMContext,
    orchestrator: Orchestrator,
    session_id: str,
    settings: Settings,
    *,
    memory_hub=None,
) -> None:
    """Refresh the system prompt, offloading I/O to a thread pool executor.

    DB queries and vector searches run in a worker thread so the event loop
    remains unblocked.  The final write to ``context.messages`` is performed
    back on the event loop for thread safety.
    """
    if not settings.progress_inject and not settings.memory_inject:
        return
    prompt = await asyncio.to_thread(
        _build_prompt, orchestrator, session_id, settings, memory_hub
    )
    _apply_prompt(context, prompt)
