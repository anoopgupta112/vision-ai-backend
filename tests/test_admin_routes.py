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

    @patch("app.admin.views.read_log_tail")
    @patch("app.admin.views.discover_features")
    @patch("app.admin.views.load_state")
    @patch("app.admin.views.load_feature_manifests")
    def test_list_automation_features_returns_manifest_and_stage_state(
        self,
        load_feature_manifests,
        load_state,
        discover_features,
        read_log_tail,
    ):
        feature = MagicMock()
        feature.id = "saved-search-alerts"
        feature.title = "Add saved search alerts"
        feature.status = "suggested"
        feature.priority = 50
        feature.backend_branch = "agent/saved-search-alerts-backend"
        feature.frontend_branch = "agent/saved-search-alerts-frontend"
        feature.acceptance_criteria = ["Enable alerts"]
        feature.api_contract = ["POST /api/lead_gen/saved-searches/:id/alerts"]
        feature.source_file = "automation/features/saved_search_alerts.json"
        feature.backend_repo = "/tmp/backend"
        feature.frontend_repo = "/tmp/frontend"
        load_feature_manifests.return_value = [feature]
        load_state.return_value = {
            "features": {
                "saved-search-alerts": {
                    "status": "in_progress",
                    "updated_at": "2026-03-20T00:00:00+00:00",
                    "stages": [
                        {
                            "name": "feature_selection",
                            "status": "done",
                            "detail": "Selected",
                            "updated_at": "2026-03-20T00:00:00+00:00",
                        }
                    ],
                }
            }
        }
        read_log_tail.return_value = ["backend_codex started", "frontend pending"]
        discover_features.return_value = [
            {
                "id": "credit-history-export",
                "title": "Add credit history export",
                "category": "data_features",
                "priority": 60,
                "branches": {
                    "backend": "agent/credit-history-export-backend",
                    "frontend": "agent/credit-history-export-frontend",
                },
                "acceptance_criteria": ["Export credit history"],
                "api_contract": ["GET /api/lead_gen/credits/history/export"],
            }
        ]

        response = self.client.get(
            "/api/admin/automation/features?backend_repo=/tmp/backend&frontend_repo=/tmp/frontend&include_exploratory=true&feature_category=data_features",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["features"][0]["id"], "saved-search-alerts")
        self.assertEqual(payload["features"][0]["run_status"], "in_progress")
        self.assertEqual(payload["features"][0]["recent_logs"][0], "backend_codex started")
        self.assertTrue(payload["features"][0]["can_approve"])
        self.assertEqual(payload["candidates"][0]["id"], "credit-history-export")
        self.assertEqual(payload["candidate_categories"][0]["key"], "data_features")
        self.assertEqual(payload["project"]["backend_repo"], "/tmp/backend")
        self.assertEqual(payload["project"]["frontend_repo"], "/tmp/frontend")
        self.assertTrue(payload["project"]["include_exploratory"])
        self.assertEqual(payload["project"]["feature_category"], "data_features")
        discover_features.assert_called_once()

    @patch("app.admin.views.load_discovery_skill")
    def test_get_automation_context_returns_discovery_skill(self, load_discovery_skill):
        load_discovery_skill.return_value = {
            "project_name": "Main Dashboard",
            "project_summary": "Lead generation platform",
            "feature_templates": [{"id": "job-retry-controls"}],
        }

        response = self.client.get("/api/admin/automation/context", headers=self.dashboard_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["context"]["project_name"], "Main Dashboard")

    @patch("app.admin.views.load_discovery_skill")
    def test_get_automation_context_uses_selected_project_scope(self, load_discovery_skill):
        load_discovery_skill.return_value = {
            "project_name": "Main Dashboard",
            "project_summary": "Lead generation platform",
            "backend_context": [],
            "frontend_context": [],
            "feature_templates": [{"id": "job-retry-controls"}],
        }

        response = self.client.get(
            "/api/admin/automation/context?project=lead_gen",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["context"]
        self.assertEqual(payload["project_name"], "Lead Generation")
        self.assertEqual(payload["project_key"], "lead_gen")
        self.assertIn("Selected backend repo:", payload["backend_context"][0])

    def test_get_automation_context_uses_analyzer_project_metadata(self):
        response = self.client.get(
            "/api/admin/automation/context?project=analyzer",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["context"]
        self.assertEqual(payload["project_name"], "hr_automatation_system")
        self.assertEqual(payload["project_key"], "analyzer")
        self.assertIn("resume analysis", payload["project_summary"].lower())

    @patch("app.admin.views.read_log_tail")
    @patch("app.admin.views.discover_features")
    @patch("app.admin.views.load_state")
    @patch("app.admin.views.load_feature_manifests")
    def test_list_automation_features_filters_tracked_features_by_backend_project_scope(
        self,
        load_feature_manifests,
        load_state,
        discover_features,
        read_log_tail,
    ):
        matching_feature = MagicMock()
        matching_feature.id = "analyzer-score-breakdown"
        matching_feature.title = "Analyzer score breakdown"
        matching_feature.status = "suggested"
        matching_feature.priority = 45
        matching_feature.backend_branch = "agent/analyzer-score-breakdown-backend"
        matching_feature.frontend_branch = "agent/analyzer-score-breakdown-frontend"
        matching_feature.acceptance_criteria = ["Show score breakdown"]
        matching_feature.api_contract = ["POST /api/analyzer/v1/match_from_pdfs"]
        matching_feature.source_file = "automation/features/analyzer_score_breakdown.json"
        matching_feature.backend_repo = "/Users/anoopchandra/repositories/main_dashboard/app/projects/analyzer"
        matching_feature.frontend_repo = "/Users/anoopchandra/repositories/main_dashboard_frontend"

        unrelated_feature = MagicMock()
        unrelated_feature.id = "payment-history-export"
        unrelated_feature.title = "Payment history export"
        unrelated_feature.status = "suggested"
        unrelated_feature.priority = 40
        unrelated_feature.backend_branch = "agent/payment-history-export-backend"
        unrelated_feature.frontend_branch = "agent/payment-history-export-frontend"
        unrelated_feature.acceptance_criteria = ["Export payment history"]
        unrelated_feature.api_contract = ["GET /api/payments/history/export"]
        unrelated_feature.source_file = "automation/features/payment_history_export.json"
        unrelated_feature.backend_repo = "/Users/anoopchandra/repositories/main_dashboard"
        unrelated_feature.frontend_repo = "/Users/anoopchandra/repositories/main_dashboard_frontend"

        load_feature_manifests.return_value = [matching_feature, unrelated_feature]
        load_state.return_value = {"features": {}}
        discover_features.return_value = []
        read_log_tail.return_value = []

        response = self.client.get(
            "/api/admin/automation/features?project=analyzer",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual([item["id"] for item in payload["features"]], ["analyzer-score-breakdown"])


    @patch("app.admin.views.update_feature_manifest_status")
    @patch("app.admin.views.save_feature_manifest")
    @patch("app.admin.views.discover_features")
    @patch("app.admin.views.load_state")
    @patch("app.admin.views.load_feature_manifests")
    def test_approve_automation_feature_updates_suggested_manifest(
        self,
        load_feature_manifests,
        load_state,
        discover_features,
        save_feature_manifest,
        update_feature_manifest_status,
    ):
        suggested = MagicMock()
        suggested.id = "saved-search-alerts"
        suggested.title = "Add saved search alerts"
        suggested.status = "suggested"
        suggested.priority = 50
        suggested.backend_branch = "agent/saved-search-alerts-backend"
        suggested.frontend_branch = "agent/saved-search-alerts-frontend"
        suggested.acceptance_criteria = ["Enable alerts"]
        suggested.api_contract = ["POST /api/lead_gen/saved-searches/:id/alerts"]
        suggested.source_file = "automation/features/saved_search_alerts.json"

        approved = MagicMock()
        approved.id = suggested.id
        approved.title = suggested.title
        approved.status = "approved"
        approved.priority = suggested.priority
        approved.backend_branch = suggested.backend_branch
        approved.frontend_branch = suggested.frontend_branch
        approved.acceptance_criteria = suggested.acceptance_criteria
        approved.api_contract = suggested.api_contract
        approved.source_file = suggested.source_file

        load_feature_manifests.side_effect = [[suggested], [approved]]
        load_state.return_value = {"features": {}}

        response = self.client.post(
            "/api/admin/automation/features/saved-search-alerts/approve",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["feature"]["status"], "approved")
        update_feature_manifest_status.assert_called_once_with(suggested, "approved")
        save_feature_manifest.assert_not_called()

    @patch("app.admin.views.update_feature_manifest_status")
    @patch("app.admin.views.save_feature_manifest")
    @patch("app.admin.views.discover_features")
    @patch("app.admin.views.load_state")
    @patch("app.admin.views.load_feature_manifests")
    def test_approve_automation_candidate_creates_manifest_then_approves_it(
        self,
        load_feature_manifests,
        load_state,
        discover_features,
        save_feature_manifest,
        update_feature_manifest_status,
    ):
        approved = MagicMock()
        approved.id = "credit-history-export"
        approved.title = "Add credit history export"
        approved.status = "suggested"
        approved.priority = 60
        approved.backend_branch = "agent/credit-history-export-backend"
        approved.frontend_branch = "agent/credit-history-export-frontend"
        approved.acceptance_criteria = ["Export credit history"]
        approved.api_contract = ["GET /api/lead_gen/credits/history/export"]
        approved.source_file = "automation/features/credit_history_export.json"

        candidate = {
            "id": "credit-history-export",
            "title": "Add credit history export",
            "status": "suggested",
            "priority": 60,
            "backend_repo": "/tmp/backend",
            "frontend_repo": "/tmp/frontend",
            "branches": {
                "backend": "agent/credit-history-export-backend",
                "frontend": "agent/credit-history-export-frontend",
            },
            "acceptance_criteria": ["Export credit history"],
            "api_contract": ["GET /api/lead_gen/credits/history/export"],
        }

        load_feature_manifests.side_effect = [[], [approved], [approved]]
        load_state.return_value = {"features": {}}
        discover_features.return_value = [candidate]

        response = self.client.post(
            "/api/admin/automation/features/credit-history-export/approve",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        save_feature_manifest.assert_called_once_with(candidate)
        update_feature_manifest_status.assert_called_once_with(approved, "approved")

    @patch("app.admin.views.append_stage_result")
    @patch("app.admin.views.mark_feature_in_progress")
    @patch("app.admin.views.subprocess.Popen")
    @patch("app.admin.views._is_feature_running")
    @patch("app.admin.views.load_feature_manifests")
    def test_run_automation_feature_starts_background_process(
        self,
        load_feature_manifests,
        is_feature_running,
        popen,
        mark_feature_in_progress,
        append_stage_result,
    ):
        approved = MagicMock()
        approved.id = "lead-website-actions"
        approved.status = "approved"
        load_feature_manifests.return_value = [approved]
        is_feature_running.return_value = False
        process = MagicMock()
        process.pid = 4321
        popen.return_value = process

        response = self.client.post(
            "/api/admin/automation/features/lead-website-actions/run",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["feature_id"], "lead-website-actions")
        popen.assert_called_once()
        mark_feature_in_progress.assert_called_once_with("lead-website-actions")
        append_stage_result.assert_called_once()

    @patch("app.admin.views._is_feature_running", return_value=True)
    @patch("app.admin.views.load_feature_manifests")
    def test_run_automation_feature_rejects_when_another_run_is_active(
        self,
        load_feature_manifests,
        _is_feature_running,
    ):
        approved = MagicMock()
        approved.id = "lead-website-actions"
        approved.status = "approved"
        load_feature_manifests.return_value = [approved]

        response = self.client.post(
            "/api/admin/automation/features/lead-website-actions/run",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "Another automation run is already active")

    def test_automation_dashboard_serves_html_shell(self):
        response = self.client.get("/api/admin/automation/dashboard", headers=self.dashboard_headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        body = response.get_data(as_text=True)
        self.assertIn("Feature Automation Board", body)
        self.assertIn("Features On This Project", body)
        self.assertIn("Suggest More Features", body)

    def test_project_dashboard_serves_html_shell(self):
        response = self.client.get(
            "/api/admin/automation/projects/lead_gen/dashboard",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn("Automation Project Detail", response.get_data(as_text=True))

    @patch("app.admin.views._automation_candidate_payload")
    @patch("app.admin.views._automation_features_payload")
    def test_get_automation_project_returns_project_payload(
        self,
        automation_features_payload,
        automation_candidate_payload,
    ):
        automation_features_payload.return_value = [{"title": "Tracked feature"}]
        automation_candidate_payload.return_value = [{"title": "Candidate feature"}]

        response = self.client.get(
            "/api/admin/automation/projects/lead_gen",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["project"]
        self.assertEqual(payload["id"], "lead_gen")
        self.assertEqual(payload["title"], "Lead Generation")
        self.assertIn("Tracked feature", payload["project_features"])

    @patch("app.admin.views._automation_candidate_payload")
    @patch("app.admin.views._automation_features_payload")
    def test_get_automation_project_live_research_returns_local_summary(
        self,
        automation_features_payload,
        automation_candidate_payload,
    ):
        automation_features_payload.return_value = [{"title": "Tracked feature"}]
        automation_candidate_payload.return_value = [{"title": "Candidate feature"}]

        response = self.client.get(
            "/api/admin/automation/projects/lead_gen/live-research",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["research"]
        self.assertIn("fetched_at", payload)
        self.assertEqual(payload["summary"]["sources_checked"], 2)

    def test_automation_dashboard_rejects_invalid_dashboard_key(self):
        response = self.client.get(
            "/api/admin/automation/dashboard",
            headers={"X-Coding-Dashboard-Key": "wrong"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Invalid dashboard key"})


if __name__ == "__main__":
    unittest.main()
