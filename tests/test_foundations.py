"""
Unit tests for the foundations endpoints.

Run with: pytest tests/
"""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import jwt

from app import create_app
from app.config import TestConfig


def _make_token(user_id: str = "admin-uuid", secret: str = TestConfig.SUPABASE_JWT_SECRET) -> str:
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": int(datetime(2099, 1, 1, tzinfo=timezone.utc).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class FoundationEndpointsTest(unittest.TestCase):

    def setUp(self):
        patcher = patch("app.extensions.create_client")
        self.mock_create_client = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_db = MagicMock()
        self.mock_create_client.return_value = self.mock_db

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self, user_id: str = "admin-uuid") -> dict:
        return {"Authorization": f"Bearer {_make_token(user_id)}"}

    def _setup_admin_role(self, user_id: str = "admin-uuid") -> None:
        role_query = MagicMock()
        role_query.execute.return_value = MagicMock(data=[{"role": "admin"}])
        (
            self.mock_db.table.return_value
            .select.return_value
            .eq.return_value
        ) = role_query

    # ------------------------------------------------------------------
    # GET /foundations/pending
    # ------------------------------------------------------------------

    def test_get_pending_requires_auth(self):
        res = self.client.get("/foundations/pending")
        self.assertEqual(res.status_code, 401)

    def test_get_pending_rejects_non_admin(self):
        user_id = "ciudadano-uuid"
        role_query = MagicMock()
        role_query.execute.return_value = MagicMock(data=[{"role": "ciudadano"}])
        (
            self.mock_db.table.return_value
            .select.return_value
            .eq.return_value
        ) = role_query

        res = self.client.get(
            "/foundations/pending",
            headers=self._auth_headers(user_id),
        )
        self.assertEqual(res.status_code, 403)

    def test_get_pending_returns_list(self):
        self._setup_admin_role()

        foundations = [
            {
                "id": "f-uuid",
                "org_name": "Patitas Felices",
                "municipio": "Bogotá",
                "phone": "3001234567",
                "status": "pending",
                "profiles": {"email": "patitas@example.com", "full_name": "Ana López"},
            }
        ]

        # The second call to the DB (after role check) is the foundations query.
        pending_query = MagicMock()
        pending_query.execute.return_value = MagicMock(data=foundations)
        (
            self.mock_db.table.return_value
            .select.return_value
            .eq.return_value
        ) = pending_query

        # Re-configure: first call → role check, second call → foundations
        call_count = {"n": 0}
        original_table = self.mock_db.table

        def table_side_effect(name):
            m = MagicMock()
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Role check query
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"role": "admin"}]
                )
            else:
                # Foundations query
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=foundations
                )
            return m

        self.mock_db.table.side_effect = table_side_effect

        res = self.client.get(
            "/foundations/pending",
            headers=self._auth_headers(),
        )
        self.assertEqual(res.status_code, 200)
        body = json.loads(res.data)
        self.assertIn("data", body)

    # ------------------------------------------------------------------
    # POST /foundations/<id>/reject — input validation
    # ------------------------------------------------------------------

    def test_reject_requires_reason(self):
        """Missing rejection_reason must return 400 before any DB call."""
        self._setup_admin_role()

        call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            call_count["n"] += 1
            if call_count["n"] == 1:
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"role": "admin"}]
                )
            return m

        self.mock_db.table.side_effect = table_side_effect

        res = self.client.post(
            "/foundations/00000000-0000-0000-0000-000000000001/reject",
            json={},
            headers=self._auth_headers(),
        )
        self.assertEqual(res.status_code, 400)
        body = json.loads(res.data)
        self.assertIn("rejection_reason", body["error"])

    def test_reject_reason_too_long(self):
        self._setup_admin_role()

        call_count = {"n": 0}

        def table_side_effect(name):
            m = MagicMock()
            call_count["n"] += 1
            if call_count["n"] == 1:
                m.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[{"role": "admin"}]
                )
            return m

        self.mock_db.table.side_effect = table_side_effect

        res = self.client.post(
            "/foundations/00000000-0000-0000-0000-000000000001/reject",
            json={"rejection_reason": "x" * 1001},
            headers=self._auth_headers(),
        )
        self.assertEqual(res.status_code, 400)

    # ------------------------------------------------------------------
    # JWT edge cases
    # ------------------------------------------------------------------

    def test_expired_token_returns_401(self):
        expired_payload = {
            "sub": "admin-uuid",
            "aud": "authenticated",
            "exp": 1,   # Unix epoch — definitely expired
            "iat": 1,
        }
        token = jwt.encode(
            expired_payload,
            TestConfig.SUPABASE_JWT_SECRET,
            algorithm="HS256",
        )
        res = self.client.get(
            "/foundations/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 401)

    def test_wrong_secret_returns_401(self):
        token = _make_token(secret="wrong-secret")
        res = self.client.get(
            "/foundations/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 401)

    def test_missing_bearer_prefix_returns_401(self):
        token = _make_token()
        res = self.client.get(
            "/foundations/pending",
            headers={"Authorization": token},  # no "Bearer " prefix
        )
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
