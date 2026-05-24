import unittest
from unittest.mock import MagicMock, patch

import app as app_module


ADMIN_USER = {
    "_id": "admin-1",
    "email": "admin@example.com",
    "is_active": True,
    "is_admin": True,
}


class AdminRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.app.config["CODING_DASHBOARD"] = "1224"
        self.client = self.app.test_client()
        self.auth_headers = {"Authorization": "Bearer valid-token"}
        self.dashboard_headers = {"X-Coding-Dashboard-Key": "1224"}

    def tearDown(self):
        self.create_indexes_patcher.stop()

    def _admin_patches(self):
        return (
            patch("app.core.middleware.decode_token", return_value={"user_id": "admin-1"}),
            patch("app.auth.models.find_user_by_id", return_value=ADMIN_USER),
        )

    @patch("app.admin.views.auth_models.list_users")
    @patch("app.admin.views.auth_models.count_users")
    @patch("app.admin.views.auth_models.to_response")
    def test_list_users_returns_serialized_users(self, to_response, count_users, list_users):
        list_users.return_value = [{"_id": "user-1"}, {"_id": "user-2"}]
        count_users.return_value = 2
        to_response.side_effect = [
            {"id": "user-1", "email": "one@example.com"},
            {"id": "user-2", "email": "two@example.com"},
        ]

        decode_token, find_user = self._admin_patches()
        with decode_token, find_user:
            response = self.client.get("/api/admin/users?limit=2&skip=5", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 2)
        self.assertEqual(response.get_json()["users"][1]["email"], "two@example.com")
        list_users.assert_called_once_with(2, 5)
        count_users.assert_called_once_with()

    @patch("app.admin.views.get_collection")
    @patch("app.admin.views.auth_models.count_users")
    def test_stats_returns_current_totals(self, count_users, get_collection):
        count_users.return_value = 7
        jobs_collection = MagicMock()
        leads_collection = MagicMock()
        jobs_collection.count_documents.return_value = 14
        leads_collection.count_documents.return_value = 88
        get_collection.side_effect = lambda name: {
            "lead_jobs": jobs_collection,
            "lead_leads": leads_collection,
        }[name]

        decode_token, find_user = self._admin_patches()
        with decode_token, find_user:
            response = self.client.get("/api/admin/stats", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"stats": {"total_users": 7, "total_jobs": 14, "total_leads": 88}},
        )

    @patch("app.admin.views.auth_models.find_user_by_id")
    @patch("app.admin.views.credits_pipeline.add_credits")
    @patch("app.admin.views.credits_model.get_balance")
    @patch("app.admin.views.credits_model.to_response")
    def test_adjust_credits_adds_balance_for_existing_user(
        self,
        to_response,
        get_balance,
        add_credits,
        find_user_by_id,
    ):
        find_user_by_id.side_effect = [ADMIN_USER, {"_id": "user-2", "email": "person@example.com"}]
        add_credits.return_value = {"_id": "credit-1"}
        get_balance.return_value = 120
        to_response.return_value = {"id": "credit-1", "amount": 50}

        decode_token = patch("app.core.middleware.decode_token", return_value={"user_id": "admin-1"})
        with decode_token, patch("app.auth.models.find_user_by_id", return_value=ADMIN_USER):
            response = self.client.post(
                "/api/admin/users/user-2/credits",
                json={"amount": 50, "note": "Promo"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["new_balance"], 120)
        add_credits.assert_called_once_with("user-2", 50, note="Promo")

    @patch("app.admin.views.credit_requests.get_pending_requests")
    @patch("app.admin.views.credit_requests.count_pending")
    @patch("app.admin.views.credit_requests.to_response")
    @patch("app.admin.views.get_collection")
    def test_list_credit_requests_returns_pending_items(
        self,
        get_collection,
        to_response,
        count_pending,
        get_pending_requests,
    ):
        get_pending_requests.return_value = [{"_id": "req-1", "user_id": "user-2"}]
        count_pending.return_value = 1
        users_collection = MagicMock()
        users_collection.find_one.return_value = {"email": "person@example.com"}
        get_collection.return_value = users_collection
        to_response.return_value = {"id": "req-1", "user_email": "person@example.com", "status": "pending"}

        decode_token, find_user = self._admin_patches()
        with decode_token, find_user:
            response = self.client.get("/api/admin/credit-requests", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["pending_count"], 1)
        self.assertEqual(response.get_json()["requests"][0]["id"], "req-1")

    @patch("app.admin.views.credit_requests.get_request_by_id")
    @patch("app.admin.views.credit_requests.approve_request")
    @patch("app.admin.views.credits_pipeline.add_credits")
    @patch("app.admin.views.auth_models.find_user_by_id")
    @patch("app.admin.views.credit_requests.to_response")
    def test_approve_credit_request_credits_user_and_returns_payload(
        self,
        to_response,
        find_user_by_id,
        add_credits,
        approve_request,
        get_request_by_id,
    ):
        get_request_by_id.return_value = {"_id": "req-1", "user_id": "user-2", "amount": 50, "status": "pending"}
        approve_request.return_value = {"_id": "req-1", "user_id": "user-2", "amount": 50, "status": "approved"}
        find_user_by_id.return_value = {"_id": "user-2", "email": "person@example.com"}
        to_response.return_value = {"id": "req-1", "status": "approved"}

        decode_token, find_user = self._admin_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/admin/credit-requests/req-1/approve",
                json={"note": "Approved for onboarding"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "50 credits added to user")
        approve_request.assert_called_once_with("req-1", "admin-1", "Approved for onboarding")
        add_credits.assert_called_once_with(
            "user-2",
            50,
            note="Credit request approved: Approved for onboarding",
        )

    @patch("app.admin.views.jobs_pipeline.retry_job")
    @patch("app.admin.views.jobs_model.to_response")
    def test_retry_job_returns_serialized_job(self, to_response, retry_job):
        retry_job.return_value = {"_id": "job-1"}
        to_response.return_value = {
            "id": "job-1",
            "query_text": "failed search",
            "leads_requested": 20,
            "leads_delivered": 0,
            "status": "queued",
            "error_message": None,
        }

        decode_token, find_user = self._admin_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/admin/jobs/job-1/retry",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["job"]["status"], "queued")
        retry_job.assert_called_once_with("job-1")




if __name__ == "__main__":
    unittest.main()
