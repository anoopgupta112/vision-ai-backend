import unittest
from unittest.mock import patch, MagicMock
from bson import ObjectId

import app as app_module
from app.projects.vip_concierge.services.cctv_service import mask_rtsp_url


class SecurityPostureTestCase(unittest.TestCase):
    """
    Automated security tests verifying:
    1. Public HTTP endpoints do not serve sensitive dotfiles or secrets.
    2. Sensitive endpoints enforce authentication.
    3. Multi-tenant data isolation is enforced (no cross-tenant IDOR).
    4. Passwords and credentials are never leaked in API responses.
    """

    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

        # Regular non-admin user
        self.decode_token_patcher = patch(
            "app.core.middleware.decode_token",
            return_value={"user_id": "user-regular-tenant-1"},
        )
        self.find_user_patcher = patch(
            "app.auth.models.find_user_by_id",
            return_value={
                "_id": "user-regular-tenant-1",
                "email": "store_manager@boutique.com",
                "is_active": True,
                "is_admin": False,
            },
        )
        self.decode_token_patcher.start()
        self.find_user_patcher.start()

        self.auth_headers = {"Authorization": "Bearer test-valid-jwt"}

    def tearDown(self):
        self.find_user_patcher.stop()
        self.decode_token_patcher.stop()
        self.create_indexes_patcher.stop()

    def test_env_file_inaccessible_over_http(self):
        """Verify .env file is never served over HTTP."""
        res = self.client.get("/.env")
        self.assertEqual(res.status_code, 404)

    def test_service_account_inaccessible_over_http(self):
        """Verify service_account.json is never served over HTTP."""
        res = self.client.get("/service_account.json")
        self.assertEqual(res.status_code, 404)

    def test_vip_matches_search_requires_auth(self):
        """Verify /matches/search rejects unauthenticated probe requests with 401."""
        res = self.client.post("/api/vip-concierge/matches/search", json={"threshold": 0.5})
        self.assertEqual(res.status_code, 401)
        self.assertIn("error", res.get_json())

    def test_vip_events_stream_requires_auth(self):
        """Verify /events/stream rejects unauthenticated SSE connections with 401."""
        res = self.client.get("/api/vip-concierge/events/stream")
        self.assertEqual(res.status_code, 401)
        self.assertIn("error", res.get_json())

    def test_vip_events_stream_accepts_query_token(self):
        """Verify /events/stream allows authentication via ?token= for EventSource compatibility."""
        res = self.client.get("/api/vip-concierge/events/stream?token=test-valid-jwt")
        # Should accept connection (200) and establish text/event-stream
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.content_type)

    def test_mask_rtsp_url_utility(self):
        """Verify RTSP URL credential masker masks passwords correctly."""
        raw_url = "rtsp://admin:SecretPass123!@192.168.1.50:554/live/ch0"
        masked = mask_rtsp_url(raw_url)
        self.assertEqual(masked, "rtsp://admin:****@192.168.1.50:554/live/ch0")
        self.assertNotIn("SecretPass123!", masked)

        # URL without credentials remains unchanged
        clean_url = "rtsp://192.168.1.50:554/live"
        self.assertEqual(mask_rtsp_url(clean_url), clean_url)

    @patch("app.projects.vip_concierge.api.routes.storage.list_cameras")
    def test_camera_credentials_masked_in_get_cameras(self, mock_list_cameras):
        """Verify GET /cameras redacts cleartext credentials in API response."""
        mock_list_cameras.return_value = [
            {
                "id": "cam-1",
                "name": "Entrance Camera",
                "rtsp_url": "rtsp://admin:MySecretCameraPass@192.168.1.100:554/stream1",
                "location": "Front Door",
                "is_active": True,
            }
        ]
        res = self.client.get("/api/vip-concierge/cameras", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        cam = data["cameras"][0]
        self.assertNotIn("MySecretCameraPass", cam["rtsp_url"])
        self.assertEqual(cam["rtsp_url"], "rtsp://admin:****@192.168.1.100:554/stream1")

    def test_admin_endpoint_forbidden_for_regular_user(self):
        """Verify non-admin users cannot access admin user management."""
        res = self.client.get("/api/admin/users", headers=self.auth_headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("Admin access required", res.get_json().get("error", ""))

    @patch("app.projects.vip_concierge.api.routes.storage.get_customer")
    def test_multi_tenant_customer_isolation(self, mock_get_customer):
        """Verify cross-tenant customer requests return 404 (IDOR prevention)."""
        # When user_id doesn't match the customer owner, storage returns None
        mock_get_customer.return_value = None

        res = self.client.get("/api/vip-concierge/customers/cust-other-tenant", headers=self.auth_headers)
        self.assertEqual(res.status_code, 404)
        mock_get_customer.assert_called_with(customer_id="cust-other-tenant", user_id="user-regular-tenant-1")


if __name__ == "__main__":
    unittest.main()

