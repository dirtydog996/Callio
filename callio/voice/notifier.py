from __future__ import annotations

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
        compact_summary = _truncate(transcript.replace("\n", " "), max_chars=320) or "会话已结束。"
    return {
        "text": f"📞 Callio 会话结束：{title}\n会话ID: {session_id}\n摘要: {compact_summary}",
    }


def notify_session_finished(
    settings: Settings,
    *,
    session_id: str,
    session_title: str,
    transcript: str,
    summary: str,
) -> None:
    payload = build_session_notification_payload(
        session_id=session_id,
        session_title=session_title,
        transcript=transcript,
        summary=summary,
    )
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
