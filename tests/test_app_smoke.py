import unittest
from unittest.mock import patch

import app as app_module


class AppSmokeTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes = self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.create_indexes_patcher.stop()

    def test_root_lists_registered_modules(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["service"], "Platform API")
        self.assertIn("auth", payload["modules"])
        self.assertIn("lead_gen", payload["modules"])
        self.assertIn("admin", payload["modules"])
        self.assertIn("payments", payload["modules"])

    def test_health_returns_healthy_status(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "healthy"})

    def test_missing_route_returns_json_404(self):
        response = self.client.get("/does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"error": "Endpoint not found"})

    def test_expected_api_routes_are_registered(self):
        rules = {rule.rule for rule in self.app.url_map.iter_rules()}

        self.assertIn("/api/auth/login", rules)
        self.assertIn("/api/auth/register", rules)
        self.assertIn("/api/lead_gen/jobs", rules)
        self.assertIn("/api/lead_gen/leads/job/<job_id>", rules)
        self.assertIn("/api/lead_gen/credits", rules)
        self.assertIn("/api/admin/stats", rules)
        self.assertIn("/api/payments/create-order", rules)


if __name__ == "__main__":
    unittest.main()
