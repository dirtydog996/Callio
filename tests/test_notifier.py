from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

from callio.config.settings import Settings


def _load_notifier_module():
    base = pathlib.Path(__file__).parent.parent / "callio" / "voice" / "notifier.py"
    spec = importlib.util.spec_from_file_location("callio.voice.notifier", base)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["callio.voice.notifier"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_notifier = _load_notifier_module()
build_session_notification_payload = _notifier.build_session_notification_payload
notify_session_finished = _notifier.notify_session_finished


class NotifierTests(unittest.TestCase):
    def test_payload_uses_summary_when_available(self) -> None:
        payload = build_session_notification_payload(
            session_id="sess-12345678",
            session_title="Demo",
            transcript="user: hi",
            summary="finished summary",
        )
        self.assertIn("finished summary", payload["text"])

    def test_payload_falls_back_to_transcript(self) -> None:
        payload = build_session_notification_payload(
            session_id="sess-12345678",
            session_title="",
            transcript="user: hi\nassistant: hello",
            summary="",
        )
        self.assertIn("user: hi assistant: hello", payload["text"])

    @patch("callio.voice.notifier.requests.post")
    def test_skip_when_no_webhook(self, post_mock) -> None:
        settings = Settings(
            notify_wechat_webhook="",
            notify_feishu_webhook="",
            notify_discord_webhook="",
            notify_telegram_webhook="",
        )
        notify_session_finished(
            settings,
            session_id="sess1",
            session_title="demo",
            transcript="user: hi",
            summary="done",
        )
        post_mock.assert_not_called()

    @patch("callio.voice.notifier.requests.post")
    def test_send_to_configured_webhooks(self, post_mock) -> None:
        post_mock.return_value.status_code = 200
        settings = Settings(
            notify_wechat_webhook="https://example.com/wechat",
            notify_discord_webhook="https://example.com/discord",
            notify_timeout_sec=6,
        )
        notify_session_finished(
            settings,
            session_id="sess1",
            session_title="demo",
            transcript="user: hi",
            summary="done",
        )
        self.assertEqual(post_mock.call_count, 2)
        called_urls = [args[0] for args, _ in post_mock.call_args_list]
        self.assertIn("https://example.com/wechat", called_urls)
        self.assertIn("https://example.com/discord", called_urls)

    @patch("callio.voice.notifier.requests.post")
    def test_notify_session_finished_inside_running_loop(self, post_mock) -> None:
        post_mock.return_value.status_code = 200
        settings = Settings(notify_wechat_webhook="https://example.com/wechat")

        async def _run() -> None:
            notify_session_finished(
                settings,
                session_id="sess1",
                session_title="demo",
                transcript="user: hi",
                summary="done",
            )
            await asyncio.sleep(0)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
