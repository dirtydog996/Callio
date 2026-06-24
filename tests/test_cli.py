from __future__ import annotations

import unittest

from app.cli.main import build_dispatch_payload, build_url, normalize_base_url


class CliTests(unittest.TestCase):
    def test_normalize_base_url(self) -> None:
        self.assertEqual(normalize_base_url("http://localhost:8000/"), "http://localhost:8000")

    def test_build_url(self) -> None:
        self.assertEqual(build_url("http://localhost:8000/", "/api/v1/health"), "http://localhost:8000/api/v1/health")

    def test_dispatch_payload_derives_title(self) -> None:
        payload = build_dispatch_payload("", "整理当前交互界面的任务清单并生成执行建议")
        self.assertEqual(payload["difficulty_level"], 1)
        self.assertEqual(payload["description"], "整理当前交互界面的任务清单并生成执行建议")
        self.assertTrue(payload["feature_name"])


if __name__ == "__main__":
    unittest.main()
