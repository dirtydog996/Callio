from __future__ import annotations

from callio.core.database import Database


def build_resume_block(database: Database, session_id: str, *, max_lines: int = 12) -> str:
    session = database.get_session(session_id)
    if not session:
        return ""

    parts: list[str] = ["[Resumed Session]"]
    title = str(session.get("title", "")).strip()
    if title:
        parts.append(f"Title: {title}")

    summary = str(session.get("summary", "")).strip()
    if summary:
        parts.append(f"Previous summary: {summary}")

    plan = str(session.get("action_plan", "")).strip()
    if plan:
        parts.append(f"Action plan:\n{plan[:600]}")

    transcript = str(session.get("transcript", "")).strip()
    if transcript:
        lines = transcript.splitlines()
        excerpt = "\n".join(lines[-max_lines:])
        parts.append(f"Recent conversation:\n{excerpt}")

    if len(parts) == 1:
        return ""
    return "\n\n".join(parts)


def parse_transcript_messages(transcript: str, *, max_turns: int = 16) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    current_role: str | None = None
    current_chunks: list[str] = []

    def _flush_current() -> None:
        nonlocal current_role, current_chunks
        if not current_role:
            return
        content = "\n".join(chunk for chunk in current_chunks if chunk).strip()
        if content:
            messages.append({"role": current_role, "content": content})
        current_role = None
        current_chunks = []

    for line in transcript.splitlines():
        text = line.strip()
        if not text:
            continue
        lower = text.lower()
        if lower.startswith("user:") or lower.startswith("user："):
            _flush_current()
            current_role = "user"
            current_chunks = [text.split(":", 1)[-1].split("：", 1)[-1].strip()]
            continue
        if lower.startswith("assistant:") or lower.startswith("assistant："):
            _flush_current()
            current_role = "assistant"
            current_chunks = [text.split(":", 1)[-1].split("：", 1)[-1].strip()]
            continue
        if current_role:
            current_chunks.append(text)

    _flush_current()
    # Keep a longer tail to reduce continuity loss when resuming sessions.
    return messages[-max(1, max_turns):]
