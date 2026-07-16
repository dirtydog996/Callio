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


def parse_transcript_messages(transcript: str, *, max_turns: int = 8) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for line in transcript.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("user:"):
            messages.append({"role": "user", "content": text[5:].strip()})
        elif text.startswith("assistant:"):
            messages.append({"role": "assistant", "content": text[10:].strip()})
    return messages[-max_turns:]
