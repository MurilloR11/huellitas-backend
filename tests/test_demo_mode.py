"""
Pruebas del modo demo: las cuentas listadas en DEMO_USER_IDS solo pueden leer
y la cuenta admin de demo no ve correos reales.

Run with: pytest tests/
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import jwt

from app import create_app
from app.config import TestConfig

DEMO_ADMIN = "demo-admin-uuid"
REAL_ADMIN = "real-admin-uuid"


class DemoConfig(TestConfig):
    DEMO_USER_IDS = f"{DEMO_ADMIN}, demo-ciudadano-uuid"


def _token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": int(datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()),
    }
    return jwt.encode(payload, TestConfig.SUPABASE_JWT_SECRET, algorithm="HS256")


class DemoModeTest(unittest.TestCase):

    def setUp(self):
        patcher = patch("app.extensions.create_client")
        self.addCleanup(patcher.stop)
        self.mock_db = MagicMock()
        patcher.start().return_value = self.mock_db

        # El rol de cualquier usuario consultado es admin
        role_query = MagicMock()
        role_query.execute.return_value = MagicMock(data=[{"role": "admin"}])
        self.mock_db.table.return_value.select.return_value.eq.return_value = role_query

        from app.shared.middleware import auth
        auth._ROLE_CACHE.clear()

        self.app = create_app(DemoConfig)
        self.client = self.app.test_client()

    def _headers(self, user_id: str) -> dict:
        return {"Authorization": f"Bearer {_token(user_id)}"}

    # --- escrituras --------------------------------------------------------

    @patch("app.features.admin.routes.service.toggle_user_ban")
    def test_demo_admin_cannot_ban_users(self, mock_ban):
        resp = self.client.post("/admin/users/someone/ban", headers=self._headers(DEMO_ADMIN))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.get_json()["demo"])
        mock_ban.assert_not_called()

    @patch("app.features.admin.routes.log_activity")
    @patch("app.features.admin.routes.service.toggle_user_ban")
    def test_real_admin_can_still_ban_users(self, mock_ban, _mock_log):
        resp = self.client.post("/admin/users/someone/ban", headers=self._headers(REAL_ADMIN))
        self.assertEqual(resp.status_code, 200)
        mock_ban.assert_called_once()

    @patch("app.features.auth.routes.log_activity", create=True)
    def test_demo_user_can_log_login_activity(self, _mock_log):
        resp = self.client.post(
            "/auth/activity", json={"action": "login"}, headers=self._headers(DEMO_ADMIN)
        )
        self.assertNotEqual(resp.status_code, 403)

    # --- lecturas ----------------------------------------------------------

    @patch("app.features.admin.routes.service.list_admin_users")
    def test_demo_admin_sees_masked_emails(self, mock_list):
        mock_list.return_value = {
            "users": [{"full_name": "Ana", "email": "ana.perez@gmail.com"}],
            "total": 1,
        }
        resp = self.client.get("/admin/users", headers=self._headers(DEMO_ADMIN))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["users"][0]["email"], "a***@gmail.com")

    @patch("app.features.admin.routes.service.list_admin_users")
    def test_real_admin_sees_full_emails(self, mock_list):
        mock_list.return_value = {
            "users": [{"full_name": "Ana", "email": "ana.perez@gmail.com"}],
            "total": 1,
        }
        resp = self.client.get("/admin/users", headers=self._headers(REAL_ADMIN))
        self.assertEqual(resp.get_json()["users"][0]["email"], "ana.perez@gmail.com")


if __name__ == "__main__":
    unittest.main()
