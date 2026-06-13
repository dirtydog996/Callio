from __future__ import annotations

from typing import TYPE_CHECKING

from callio.config.settings import Settings
from callio.voice.memory_context import build_memory_block
from callio.voice.prompt import build_system_prompt
from callio.voice.resume_context import build_resume_block

if TYPE_CHECKING:
    from callio.orchestrator import Orchestrator
    from pipecat.processors.aggregators.llm_context import LLMContext


def refresh_system_prompt(
    context: LLMContext,
    orchestrator: Orchestrator,
    session_id: str,
    settings: Settings,
    *,
    memory_hub=None,
) -> None:
    if not settings.progress_inject and not settings.memory_inject:
        return
    progress_block = ""
    memory_block = ""
    if settings.progress_inject:
        progress_block = orchestrator.progress.build_context_block(session_id)
    if settings.memory_inject and memory_hub is not None:
        memory_block = build_memory_block(memory_hub, orchestrator.database)
    resume_block = build_resume_block(orchestrator.database, session_id)
    prompt = build_system_prompt(
        settings.voice_response_limit,
        progress_block=progress_block,
        memory_block=memory_block,
        resume_block=resume_block,
    )
    messages = context.messages
    if not messages:
        context.messages = [{"role": "system", "content": prompt}]
        return
    if messages[0].get("role") == "system":
        messages[0]["content"] = prompt
    else:
        messages.insert(0, {"role": "system", "content": prompt})
