from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


def _load_resume_context_module():
    base = pathlib.Path(__file__).parent.parent / "callio" / "voice"
    spec = importlib.util.spec_from_file_location("callio.voice.resume_context", base / "resume_context.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["callio.voice.resume_context"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


parse_transcript_messages = _load_resume_context_module().parse_transcript_messages


class ResumeContextTests(unittest.TestCase):
    def test_parse_transcript_messages_keeps_recent_turns(self) -> None:
        transcript_lines: list[str] = []
        for i in range(20):
            transcript_lines.append(f"user: q{i}")
            transcript_lines.append(f"assistant: a{i}")
        messages = parse_transcript_messages("\n".join(transcript_lines), max_turns=16)
        self.assertEqual(len(messages), 16)
        self.assertEqual(messages[0], {"role": "user", "content": "q12"})
        self.assertEqual(messages[-1], {"role": "assistant", "content": "a19"})

    def test_parse_transcript_messages_supports_multiline_blocks(self) -> None:
        transcript = "\n".join(
            [
                "user: first line",
                "second line",
                "assistant: reply one",
                "continued",
            ]
        )
        messages = parse_transcript_messages(transcript, max_turns=8)
        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "first line\nsecond line"},
                {"role": "assistant", "content": "reply one\ncontinued"},
            ],
        )

    def test_parse_transcript_messages_supports_fullwidth_colon(self) -> None:
        transcript = "\n".join(["user：你好", "assistant：你好，请继续"])
        messages = parse_transcript_messages(transcript)
        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好，请继续"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
