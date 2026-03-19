import unittest
from unittest.mock import patch

import app as app_module


class AuthAndPermissionsTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.create_indexes_patcher.stop()

    def test_register_requires_email_and_password(self):
        response = self.client.post("/api/auth/register", json={"email": ""})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Email and password are required"})

    def test_register_rejects_short_passwords(self):
        response = self.client.post(
            "/api/auth/register",
            json={"email": "person@example.com", "password": "123"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Password must be at least 6 characters"},
        )

    @patch("app.auth.views.services.register_user")
    def test_register_returns_service_payload(self, register_user):
        register_user.return_value = {
            "message": "Registration initiated. Please verify your email.",
            "pending_id": "pending-1",
            "email": "person@example.com",
            "requires_verification": True,
        }

        response = self.client.post(
            "/api/auth/register",
            json={"email": "person@example.com", "password": "secret123"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["requires_verification"])
        register_user.assert_called_once_with("person@example.com", "secret123", None)

    def test_login_requires_email_and_password(self):
        response = self.client.post("/api/auth/login", json={"email": "person@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Email and password are required"})

    @patch("app.auth.views.services.login_user")
    def test_login_returns_token_and_user_payload(self, login_user):
        login_user.return_value = {
            "token": "token-123",
            "user": {"id": "user-1", "email": "person@example.com"},
        }

        response = self.client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": "secret123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["token"], "token-123")
        login_user.assert_called_once_with("person@example.com", "secret123")

    def test_profile_requires_authorization_header(self):
        response = self.client.get("/api/auth/profile")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Authorization required"})

    @patch("app.core.middleware.decode_token", return_value=None)
    def test_profile_rejects_invalid_token(self, decode_token):
        response = self.client.get(
            "/api/auth/profile",
            headers={"Authorization": "Bearer invalid-token"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Invalid or expired token"})
        decode_token.assert_called_once_with("invalid-token")

    @patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"})
    @patch("app.auth.models.find_user_by_id", return_value={"_id": "user-1", "is_active": False})
    def test_profile_blocks_disabled_users(self, find_user_by_id, decode_token):
        response = self.client.get(
            "/api/auth/profile",
            headers={"Authorization": "Bearer valid-token"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Account is disabled"})
        decode_token.assert_called_once_with("valid-token")
        find_user_by_id.assert_called_once_with("user-1")

    @patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"})
    @patch(
        "app.auth.models.find_user_by_id",
        return_value={
            "_id": "user-1",
            "email": "person@example.com",
            "phone": None,
            "email_verified": True,
            "phone_verified": False,
            "is_admin": False,
            "is_active": True,
            "created_at": None,
        },
    )
    def test_profile_returns_authenticated_user(self, find_user_by_id, decode_token):
        response = self.client.get(
            "/api/auth/profile",
            headers={"Authorization": "Bearer valid-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["email"], "person@example.com")
        decode_token.assert_called_once_with("valid-token")
        find_user_by_id.assert_called_once_with("user-1")

    @patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"})
    @patch(
        "app.auth.models.find_user_by_id",
        return_value={"_id": "user-1", "email": "person@example.com", "is_active": True, "is_admin": False},
    )
    def test_admin_stats_requires_admin_access(self, find_user_by_id, decode_token):
        response = self.client.get(
            "/api/admin/stats",
            headers={"Authorization": "Bearer valid-token"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Admin access required"})
        decode_token.assert_called_once_with("valid-token")
        find_user_by_id.assert_called_once_with("user-1")


if __name__ == "__main__":
    unittest.main()
