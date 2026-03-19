import unittest
from unittest.mock import patch

import app as app_module


AUTH_USER = {
    "_id": "user-1",
    "email": "person@example.com",
    "is_active": True,
    "is_admin": False,
}


class LeadGenRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.create_indexes_patcher = patch.object(app_module, "create_indexes")
        self.create_indexes_patcher.start()
        self.app = app_module.create_app()
        self.client = self.app.test_client()
        self.auth_headers = {"Authorization": "Bearer valid-token"}

    def tearDown(self):
        self.create_indexes_patcher.stop()

    def _auth_patches(self):
        return (
            patch("app.core.middleware.decode_token", return_value={"user_id": "user-1"}),
            patch("app.auth.models.find_user_by_id", return_value=AUTH_USER),
        )

    def test_create_job_requires_authentication(self):
        response = self.client.post("/api/lead_gen/jobs", json={"query": "plumbers", "limit": 10})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Authorization required"})

    def test_create_job_validates_required_query(self):
        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/jobs",
                json={"query": "", "limit": 10},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Query is required"})

    def test_create_job_validates_limit_bounds(self):
        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/jobs",
                json={"query": "plumbers in mumbai", "limit": 0},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Limit must be a positive integer"})

        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/jobs",
                json={"query": "plumbers in mumbai", "limit": 501},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Maximum 500 leads per job"})

    @patch("app.lead_gen.jobs.routes.pipeline.create_job")
    @patch("app.lead_gen.jobs.routes.model.to_response")
    def test_create_job_returns_serialized_job(self, to_response, create_job):
        create_job.return_value = {"_id": "job-1"}
        to_response.return_value = {
            "id": "job-1",
            "query_text": "plumbers in mumbai",
            "leads_requested": 10,
            "leads_delivered": 0,
            "status": "queued",
        }

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/jobs",
                json={"query": "plumbers in mumbai", "limit": 10},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["job"]["id"], "job-1")
        create_job.assert_called_once_with("user-1", "plumbers in mumbai", 10)

    @patch("app.lead_gen.jobs.routes.model.find_by_user")
    @patch("app.lead_gen.jobs.routes.model.to_response")
    def test_list_jobs_uses_current_user_and_pagination(self, to_response, find_by_user):
        find_by_user.return_value = [{"_id": "job-1"}, {"_id": "job-2"}]
        to_response.side_effect = [
            {"id": "job-1", "query_text": "plumbers in mumbai"},
            {"id": "job-2", "query_text": "restaurants in delhi"},
        ]

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.get(
                "/api/lead_gen/jobs?limit=2&skip=5",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 2)
        self.assertEqual(response.get_json()["jobs"][0]["id"], "job-1")
        find_by_user.assert_called_once_with("user-1", 2, 5)

    @patch("app.lead_gen.jobs.routes.pipeline.retry_user_job")
    @patch("app.lead_gen.jobs.routes.model.to_response")
    def test_retry_job_returns_serialized_job(self, to_response, retry_user_job):
        retry_user_job.return_value = {"_id": "job-1"}
        to_response.return_value = {
            "id": "job-1",
            "query_text": "plumbers in mumbai",
            "leads_requested": 10,
            "leads_delivered": 0,
            "status": "queued",
            "error_message": None,
        }

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.post(
                "/api/lead_gen/jobs/job-1/retry",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["job"]["status"], "queued")
        retry_user_job.assert_called_once_with("job-1", "user-1")

    @patch("app.lead_gen.leads.routes.pipeline.get_leads_for_job")
    def test_download_csv_returns_expected_headers_and_rows(self, get_leads_for_job):
        get_leads_for_job.return_value = [
            {
                "name": "ACME Plumbing",
                "phone": "1234567890",
                "email": "hello@example.com",
                "website": "https://example.com",
                "address": "Mumbai",
            }
        ]

        decode_token, find_user = self._auth_patches()
        with decode_token, find_user:
            response = self.client.get(
                "/api/lead_gen/leads/job/job-1/download",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertIn("attachment; filename=leads_job-1.csv", response.headers["Content-Disposition"])
        csv_text = response.get_data(as_text=True)
        self.assertIn("Name,Phone,Email,Website,Address", csv_text)
        self.assertIn("ACME Plumbing,1234567890,hello@example.com,https://example.com,Mumbai", csv_text)
        get_leads_for_job.assert_called_once_with("job-1", "user-1", limit=10000)


if __name__ == "__main__":
    unittest.main()
