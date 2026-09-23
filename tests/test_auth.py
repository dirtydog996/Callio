from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from callio.config.settings import Settings
    from callio.core.auth import generate_token, hash_token
    from callio.core.server import create_app
except ImportError:  # pragma: no cover - optional dependency in lean environments
    TestClient = None
    Settings = None
    generate_token = None
    create_app = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(TestClient is None or Settings is None or create_app is None, "fastapi runtime not installed")
class AuthTests(unittest.TestCase):
    def _make_client(self, **auth_kwargs) -> TestClient:
        self.tmpdir = tempfile.TemporaryDirectory()
        settings = Settings(
            db_path=str(Path(self.tmpdir.name) / "callio.db"),
            app_dir=str(ROOT / "app"),
            static_dir=str(ROOT / "app" / "web"),
            mobile_dir=str(ROOT / "app" / "mobile"),
            shared_dir=str(ROOT / "app" / "shared"),
            **auth_kwargs,
        )
        client = TestClient(create_app(settings))
        client.app.state.database.initialize()
        self.db = client.app.state.database
        return client

    def tearDown(self) -> None:
        self.client.close()
        self.tmpdir.cleanup()

    def _add_token(self, token: str, label: str = "test") -> None:
        self.db.create_api_token(hash_token(token), label)

    def test_auth_disabled_allows_anonymous(self) -> None:
        self.client = self._make_client()
        self.assertEqual(self.client.get("/api/v1/tasks").status_code, 200)

    def test_enabled_rejects_missing_or_invalid_token(self) -> None:
        self.client = self._make_client(auth_enabled=True)
        self.assertEqual(self.client.get("/api/v1/tasks").status_code, 401)
        self.assertEqual(
            self.client.get("/api/v1/tasks", headers={"Authorization": "Bearer wrong"}).status_code,
            401,
        )

    def test_valid_bearer_token_passes(self) -> None:
        self.client = self._make_client(auth_enabled=True)
        self._add_token("cio_secret123")
        response = self.client.get("/api/v1/tasks", headers={"Authorization": "Bearer cio_secret123"})
        self.assertEqual(response.status_code, 200)

    def test_revoked_token_rejected(self) -> None:
        self.client = self._make_client(auth_enabled=True)
        self._add_token("cio_revoked")
        self.db.revoke_api_token(hash_token("cio_revoked"))
        response = self.client.get("/api/v1/tasks", headers={"Authorization": "Bearer cio_revoked"})
        self.assertEqual(response.status_code, 401)

    def test_health_open_when_enabled(self) -> None:
        self.client = self._make_client(auth_enabled=True)
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)

    def test_bootstrap_env_token(self) -> None:
        self.client = self._make_client(auth_enabled=True, bootstrap_token="bt_recover")
        response = self.client.get("/api/v1/tasks", headers={"Authorization": "Bearer bt_recover"})
        self.assertEqual(response.status_code, 200)

    def test_token_lifecycle_api(self) -> None:
        self.client = self._make_client(auth_enabled=True, bootstrap_token="bt_recover")
        headers = {"Authorization": "Bearer bt_recover"}

        created = self.client.post("/api/v1/tokens", json={"label": "ios"}, headers=headers)
        self.assertEqual(created.status_code, 200)
        token = created.json()["token"]
        self.assertTrue(token.startswith("cio_"))

        # plaintext token works on a business API
        used = self.client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(used.status_code, 200)

        # listing never leaks the plaintext
        listed = self.client.get("/api/v1/tokens", headers=headers)
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertNotIn(token, listed.text)

        # revoke -> original token rejected
        revoked = self.client.delete(f"/api/v1/tokens/{items[0]['token_hash']}", headers=headers)
        self.assertEqual(revoked.status_code, 200)
        after = self.client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(after.status_code, 401)
        self.assertEqual(
            self.client.delete(f"/api/v1/tokens/{items[0]['token_hash']}", headers=headers).status_code,
            404,
        )

    def test_websocket_query_param(self) -> None:
        self.client = self._make_client(auth_enabled=True)
        self._add_token("cio_ws_ok")
        with self.client.websocket_connect("/ws/status?token=cio_ws_ok") as ws:
            snapshot = ws.receive_json()
            self.assertEqual(snapshot["event"], "SNAPSHOT")
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/status?token=wrong"):
                pass

    def test_generate_token_format(self) -> None:
        token = generate_token()
        self.assertTrue(token.startswith("cio_"))
        self.assertEqual(len(token), 4 + 40)
        self.assertNotEqual(token, generate_token())


if __name__ == "__main__":
    unittest.main()
