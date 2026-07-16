from __future__ import annotations

import unittest

from callio.config.settings import Settings
from callio.web import MOBILE_CLIENT_PATH, MOBILE_DIR, SHARED_DIR, WEB_CLIENT_PATH, WEB_DIR


class ClientPathTests(unittest.TestCase):
    def test_client_routes_are_under_app_namespace(self) -> None:
        self.assertEqual(WEB_CLIENT_PATH, "/app/web/index.html")
        self.assertEqual(MOBILE_CLIENT_PATH, "/app/mobile/index.html")

    def test_default_settings_point_to_new_app_structure(self) -> None:
        settings = Settings()
        self.assertEqual(settings.static_dir, str(WEB_DIR))
        self.assertEqual(settings.mobile_dir, str(MOBILE_DIR))
        self.assertEqual(settings.shared_dir, str(SHARED_DIR))


if __name__ == "__main__":
    unittest.main()
