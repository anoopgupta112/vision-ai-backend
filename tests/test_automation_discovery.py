import json
import tempfile
import unittest
from pathlib import Path

from automation.discovery import discover_features, discover_project_templates


class DiscoveryTests(unittest.TestCase):
    def test_discovery_writes_suggested_feature_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as backend_dir, tempfile.TemporaryDirectory() as frontend_dir, tempfile.TemporaryDirectory() as features_dir:
            backend = Path(backend_dir)
            frontend = Path(frontend_dir)
            features = Path(features_dir)

            self._touch(backend / "app/lead_gen/jobs/routes.py")
            self._touch(backend / "app/admin/views.py")
            self._touch(frontend / "src/features/lead-gen/components/JobsList.tsx")
            self._touch(frontend / "src/features/admin-dashboard/pages/AdminPage.tsx")

            suggestions = discover_features(backend, frontend, features, write=True)

            self.assertEqual(1, len(suggestions))
            manifest_path = features / "job_retry_controls.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual("suggested", manifest["status"])
            self.assertEqual("agent/job-retry-controls-backend", manifest["branches"]["backend"])

    def test_discovery_returns_multiple_suggestions_from_project_context(self) -> None:
        with tempfile.TemporaryDirectory() as backend_dir, tempfile.TemporaryDirectory() as frontend_dir, tempfile.TemporaryDirectory() as features_dir:
            backend = Path(backend_dir)
            frontend = Path(frontend_dir)
            features = Path(features_dir)

            backend_files = [
                "app/lead_gen/jobs/routes.py",
                "app/admin/views.py",
                "app/payments/routes.py",
                "app/lead_gen/credits/routes.py",
                "app/lead_gen/saved_searches/routes.py",
                "app/lead_gen/leads/routes.py",
            ]
            frontend_files = [
                "src/features/lead-gen/components/JobsList.tsx",
                "src/features/admin-dashboard/pages/AdminPage.tsx",
                "src/features/lead-gen/pages/PaymentHistoryPage.tsx",
                "src/features/lead-gen/api/paymentsApi.ts",
                "src/features/lead-gen/components/SavedSearchesPanel.tsx",
                "src/features/lead-gen/components/LeadsTable.tsx",
                "src/features/lead-gen/components/CreditsHistory.tsx",
                "src/features/lead-gen/api/creditsApi.ts",
                "src/features/admin-dashboard/api/adminApi.ts",
            ]
            for path in backend_files:
                self._touch(backend / path)
            for path in frontend_files:
                self._touch(frontend / path)

            suggestions = discover_features(backend, frontend, features, write=False)

            self.assertGreaterEqual(len(suggestions), 5)
            ids = {item["id"] for item in suggestions}
            self.assertIn("job-retry-controls", ids)
            self.assertIn("payment-history-export", ids)
            self.assertIn("saved-search-alerts", ids)
            self.assertIn("credit-history-export", ids)
            self.assertIn("admin-user-filters", ids)

    def test_discovery_skips_existing_feature_ids(self) -> None:
        with tempfile.TemporaryDirectory() as backend_dir, tempfile.TemporaryDirectory() as frontend_dir, tempfile.TemporaryDirectory() as features_dir:
            backend = Path(backend_dir)
            frontend = Path(frontend_dir)
            features = Path(features_dir)

            self._touch(backend / "app/lead_gen/jobs/routes.py")
            self._touch(backend / "app/admin/views.py")
            self._touch(frontend / "src/features/lead-gen/components/JobsList.tsx")
            self._touch(frontend / "src/features/admin-dashboard/pages/AdminPage.tsx")
            (features / "existing.json").write_text(
                json.dumps(
                    {
                        "id": "job-retry-controls",
                        "title": "Existing",
                        "status": "approved",
                        "priority": 1,
                        "backend_repo": str(backend),
                        "frontend_repo": str(frontend),
                        "branches": {"backend": "agent/existing-backend", "frontend": "agent/existing-frontend"},
                        "acceptance_criteria": ["Keep existing feature"],
                        "api_contract": ["POST /existing"],
                    }
                )
            )

            suggestions = discover_features(backend, frontend, features, write=True)

            self.assertEqual([], suggestions)
            self.assertFalse((features / "job_retry_controls.json").exists())

    def test_discovery_generates_field_driven_data_and_ai_features(self) -> None:
        with tempfile.TemporaryDirectory() as backend_dir, tempfile.TemporaryDirectory() as frontend_dir, tempfile.TemporaryDirectory() as features_dir:
            backend = Path(backend_dir)
            frontend = Path(frontend_dir)
            features = Path(features_dir)

            self._touch(
                backend / "app/lead_gen/leads/model.py",
                "phone = True\nwebsite = True\naddress = True\n"
            )
            self._touch(
                frontend / "src/features/lead-gen/components/LeadsTable.tsx",
                "const columns = ['phone', 'website', 'address'];\n"
            )

            suggestions = discover_features(backend, frontend, features, write=False)

            ids = {item["id"] for item in suggestions}
            by_id = {item["id"]: item for item in suggestions}
            self.assertIn("lead-phone-actions", ids)
            self.assertIn("lead-website-actions", ids)
            self.assertIn("lead-address-map-actions", ids)
            self.assertIn("ai-lead-contact-assistant", ids)
            self.assertEqual(by_id["lead-phone-actions"]["category"], "data_features")
            self.assertEqual(by_id["ai-lead-contact-assistant"]["category"], "ai_support")

    def test_project_discovery_search_depth_returns_more_results(self) -> None:
        shallow = discover_project_templates(include_exploratory=True, limit=None, search_depth=1)
        deeper = discover_project_templates(include_exploratory=True, limit=None, search_depth=4)

        self.assertGreater(len(deeper), len(shallow))
        shallow_ids = {item["id"] for item in shallow}
        deeper_ids = {item["id"] for item in deeper}
        self.assertTrue(shallow_ids.issubset(deeper_ids))

    def _touch(self, path: Path, content: str = "// test fixture\n") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


if __name__ == "__main__":
    unittest.main()
