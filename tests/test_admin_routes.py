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
            "jobs": jobs_collection,
            "leads": leads_collection,
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
    @patch("app.admin.views.discover_project_templates")
    @patch("app.admin.views.discover_features")
    @patch("app.admin.views.load_state")
    @patch("app.admin.views.load_feature_manifests")
    def test_list_automation_features_returns_manifest_and_stage_state(
        self,
        load_feature_manifests,
        load_state,
        discover_features,
        discover_project_templates,
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
        discover_project_templates.return_value = [
            {
                "id": "lead-gen-marketing-site",
                "title": "Lead Generation Marketing Site",
                "priority": 10,
                "summary": "Standalone marketing site",
                "why_now": "No public acquisition flow yet",
                "suggested_pages": ["Landing page", "Pricing page"],
            }
        ]

        response = self.client.get(
            "/api/admin/automation/features?backend_repo=/tmp/backend&frontend_repo=/tmp/frontend&include_exploratory=true&feature_category=data_features&include_project_exploratory=true&project_search_depth=2",
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
        self.assertEqual(payload["project_candidates"][0]["id"], "lead-gen-marketing-site")
        self.assertEqual(payload["project"]["backend_repo"], "/tmp/backend")
        self.assertEqual(payload["project"]["frontend_repo"], "/tmp/frontend")
        self.assertTrue(payload["project"]["include_exploratory"])
        self.assertEqual(payload["project"]["feature_category"], "data_features")
        self.assertTrue(payload["project"]["include_project_exploratory"])
        self.assertEqual(payload["project"]["project_limit"], 3)
        self.assertEqual(payload["project"]["project_search_depth"], 2)
        self.assertEqual(payload["project"]["project_total_available"], 1)
        discover_features.assert_called_once()
        discover_project_templates.assert_called_once_with(include_exploratory=True, limit=None, search_depth=2)

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

    @patch("app.admin.views.discover_project_templates")
    def test_get_automation_project_returns_project_detail(self, discover_project_templates):
        discover_project_templates.return_value = [
            {
                "id": "ai-search-ops-studio",
                "title": "AI Search Operations Studio",
                "priority": 60,
                "summary": "AI-assisted search operations product",
                "why_now": "Natural extension of the search workflow",
                "market_value": "High value for operator workflows",
                "market_research": ["Teams need search tuning support"],
                "growth_chances": ["Can grow into premium ops tooling"],
                "benefits": ["Better search quality"],
                "future_scope_ai": ["AI query rewrite suggestions"],
                "project_features": ["Saved-search optimizer"],
                "suggested_pages": ["Search strategy dashboard"],
            }
        ]

        response = self.client.get(
            "/api/admin/automation/projects/ai-search-ops-studio?include_project_exploratory=true&project_search_depth=4",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["project"]["id"], "ai-search-ops-studio")
        discover_project_templates.assert_called_once_with(include_exploratory=True, limit=None, search_depth=4)

    @patch("app.admin.views.get_live_project_research")
    def test_get_automation_project_live_research_returns_payload(self, get_live_project_research):
        get_live_project_research.return_value = {
            "project_id": "ai-search-ops-studio",
            "fetched_at": "2026-03-20T00:00:00+00:00",
            "sources": [{"label": "OpenAI API pricing", "status": "ok"}],
            "summary": {"sources_checked": 1, "sources_available": 1, "market_signals": ["Pricing page is available"]},
            "competitor_snapshot": [],
        }

        response = self.client.get(
            "/api/admin/automation/projects/ai-search-ops-studio/live-research?include_project_exploratory=true&project_search_depth=5",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["research"]["project_id"], "ai-search-ops-studio")
        get_live_project_research.assert_called_once_with(
            "ai-search-ops-studio",
            include_project_exploratory=True,
            project_search_depth=5,
        )

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
        self.assertIn("Project Automation Board", body)
        self.assertIn("Project Features", body)
        self.assertIn("Projects", body)
        self.assertIn("Suggest More Features", body)
        self.assertIn("Suggest More Projects", body)
        self.assertIn("Project Suggestions", body)

    def test_automation_project_dashboard_serves_html_shell(self):
        response = self.client.get(
            "/api/admin/automation/projects/ai-search-ops-studio/dashboard",
            headers=self.dashboard_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        body = response.get_data(as_text=True)
        self.assertIn("Automation Project Detail", body)
        self.assertIn("Future Scope With AI", body)
        self.assertIn("Competitors In Market", body)
        self.assertIn("Live Market Research", body)

    def test_automation_dashboard_rejects_invalid_dashboard_key(self):
        response = self.client.get(
            "/api/admin/automation/dashboard",
            headers={"X-Coding-Dashboard-Key": "wrong"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), {"error": "Invalid dashboard key"})


if __name__ == "__main__":
    unittest.main()
