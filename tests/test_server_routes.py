from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from callio.config.settings import Settings
    from callio.core.server import create_app
except ImportError:  # pragma: no cover - optional dependency in lean environments
    TestClient = None
    Settings = None
    create_app = None


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(TestClient is None or Settings is None or create_app is None, "fastapi runtime not installed")
class ServerRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.settings = Settings(
            db_path=str(Path(self.tmpdir.name) / "callio.db"),
            app_dir=str(ROOT / "app"),
            static_dir=str(ROOT / "app" / "web"),
            mobile_dir=str(ROOT / "app" / "mobile"),
            shared_dir=str(ROOT / "app" / "shared"),
        )
        self.client = TestClient(create_app(self.settings))
        self.client.app.state.database.initialize()

    def tearDown(self) -> None:
        self.client.close()
        self.tmpdir.cleanup()

    def test_root_redirects_to_web_app(self) -> None:
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/app/web/index.html")

    def test_web_and_mobile_clients_are_served(self) -> None:
        web_response = self.client.get("/app/web/index.html")
        mobile_response = self.client.get("/app/mobile/index.html")
        shared_response = self.client.get("/app/shared/client.js")
        self.assertEqual(web_response.status_code, 200)
        self.assertIn("Copilot-style Workspace", web_response.text)
        self.assertEqual(mobile_response.status_code, 200)
        self.assertIn("Mobile Workspace", mobile_response.text)
        self.assertEqual(shared_response.status_code, 200)
        self.assertIn("startSession", shared_response.text)

    def test_clear_all_sessions_route_removes_stored_history(self) -> None:
        create_response = self.client.post("/api/v1/sessions", json={
            "session_id": "session-1",
            "title": "Demo Session",
            "transcript": "user: hello",
            "summary": "demo",
        })
        self.assertEqual(create_response.status_code, 200)

        before = self.client.get("/api/v1/sessions")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(len(before.json()["items"]), 1)

        clear_response = self.client.delete("/api/v1/sessions")
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(clear_response.json()["status"], "cleared")
        self.assertEqual(clear_response.json()["counts"]["sessions"], 1)

        after = self.client.get("/api/v1/sessions")
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.json()["items"], [])


if __name__ == "__main__":
    unittest.main()
