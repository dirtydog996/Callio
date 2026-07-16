from __future__ import annotations

import asyncio
import logging
from typing import Any

import requests

from callio.config.settings import Settings

logger = logging.getLogger(__name__)


def _targets(settings: Settings) -> list[tuple[str, str]]:
    return [
        ("wechat", settings.notify_wechat_webhook),
        ("feishu", settings.notify_feishu_webhook),
        ("discord", settings.notify_discord_webhook),
        ("telegram", settings.notify_telegram_webhook),
    ]


def _truncate(text: str, max_chars: int = 360) -> str:
    clean = (text or "").strip()
    if len(clean) <= max_chars:
        return clean
    return f"{clean[:max_chars]}…"


def build_session_notification_payload(
    *,
    session_id: str,
    session_title: str,
    transcript: str,
    summary: str,
) -> dict[str, str]:
    title = session_title.strip() or session_id[:8]
    compact_summary = _truncate(summary, max_chars=320)
    if not compact_summary:
        compact_summary = _truncate(transcript.replace("\n", " "), max_chars=320) or "Session ended."
    return {
        "text": f"📞 Callio session ended: {title}\nSession ID: {session_id}\nSummary: {compact_summary}",
    }


def _send_notifications_sync(
    settings: Settings,
    payload: dict[str, str],
) -> None:
    """Send webhook notifications synchronously (intended to run in a thread)."""
    for channel, webhook in _targets(settings):
        if not webhook:
            continue
        try:
            response = requests.post(
                webhook,
                json=payload,
                timeout=max(1, settings.notify_timeout_sec),
            )
            if response.status_code >= 400:
                logger.warning("Notify %s failed: HTTP %s", channel, response.status_code)
        except Exception as exc:
            logger.warning("Notify %s failed: %s", channel, exc)


def notify_session_finished(
    settings: Settings,
    *,
    session_id: str,
    session_title: str,
    transcript: str,
    summary: str,
) -> None:
    """Schedule webhook notifications without blocking the event loop.

    If called from a running asyncio event loop the HTTP calls are offloaded
    to a thread pool via ``asyncio.create_task``.  Outside an event loop they
    are executed synchronously (e.g. in tests or CLI scripts).
    """
    payload = build_session_notification_payload(
        session_id=session_id,
        session_title=session_title,
        transcript=transcript,
        summary=summary,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        asyncio.create_task(
            loop.run_in_executor(None, _send_notifications_sync, settings, payload)
        )
    else:
        _send_notifications_sync(settings, payload)
