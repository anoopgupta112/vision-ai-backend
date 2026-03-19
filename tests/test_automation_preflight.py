import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.models import FeatureManifest
from automation.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_preflight_passes_for_codex_only_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as backend_dir, tempfile.TemporaryDirectory() as frontend_dir:
            Path(backend_dir, ".git").mkdir()
            Path(frontend_dir, ".git").mkdir()
            feature = self._feature(backend_dir, frontend_dir)

            with patch.dict(
                os.environ,
                {
                    "AUTOMATION_WEBHOOK_URL": "https://example.com/webhook",
                },
                clear=False,
            ), patch("automation.preflight.shutil.which", return_value="/usr/bin/fake"), patch(
                "automation.preflight._run_command"
            ) as run_command:
                run_command.return_value.returncode = 0
                run_command.return_value.stdout = "ok"
                run_command.return_value.stderr = ""

                result = run_preflight(feature, require_codex=True, require_webhook=True)

        self.assertEqual("done", result.status)

    def test_preflight_fails_when_github_auth_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as backend_dir, tempfile.TemporaryDirectory() as frontend_dir:
            Path(backend_dir, ".git").mkdir()
            Path(frontend_dir, ".git").mkdir()
            feature = self._feature(backend_dir, frontend_dir)

            with patch.dict(os.environ, {}, clear=True), patch("automation.preflight.shutil.which", return_value="/usr/bin/fake"), patch(
                "automation.preflight._run_command"
            ) as run_command:
                run_command.return_value.returncode = 1
                run_command.return_value.stdout = ""
                run_command.return_value.stderr = "not logged in"

                result = run_preflight(feature, require_github=True, require_webhook=True)

        self.assertEqual("failed", result.status)
        self.assertIn("not logged in", result.detail)
        self.assertIn("AUTOMATION_WEBHOOK_URL", result.detail)

    def _feature(self, backend_dir: str, frontend_dir: str) -> FeatureManifest:
        return FeatureManifest(
            id="preflight-feature",
            title="Preflight Feature",
            status="approved",
            priority=1,
            backend_repo=backend_dir,
            frontend_repo=frontend_dir,
            backend_branch="agent/preflight-backend",
            frontend_branch="agent/preflight-frontend",
            acceptance_criteria=["Criterion"],
            api_contract=["POST /api/test"],
            source_file="automation/features/preflight_feature.json",
        )


if __name__ == "__main__":
    unittest.main()
