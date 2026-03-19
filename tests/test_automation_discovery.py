import json
import tempfile
import unittest
from pathlib import Path

from automation.discovery import discover_features


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

    def _touch(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// test fixture\n")


if __name__ == "__main__":
    unittest.main()
