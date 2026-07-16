from __future__ import annotations

import unittest

from app.cli.main import build_dispatch_payload, build_url, normalize_base_url


class CliTests(unittest.TestCase):
    def test_normalize_base_url(self) -> None:
        self.assertEqual(normalize_base_url("http://localhost:8000/"), "http://localhost:8000")

    def test_build_url(self) -> None:
        self.assertEqual(build_url("http://localhost:8000/", "/api/v1/health"), "http://localhost:8000/api/v1/health")

    def test_dispatch_payload_derives_title(self) -> None:
        payload = build_dispatch_payload("", "Reorganize the current UI task list and generate execution recommendations")
        self.assertEqual(payload["difficulty_level"], 1)
        self.assertEqual(payload["description"], "Reorganize the current UI task list and generate execution recommendations")
        self.assertTrue(payload["feature_name"])


if __name__ == "__main__":
    unittest.main()
