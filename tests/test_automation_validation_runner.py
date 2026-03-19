import unittest
from unittest.mock import patch

from automation.models import FeatureManifest
from automation.validation_runner import execute_validation_run


class ValidationRunnerTests(unittest.TestCase):
    def test_fails_when_backend_code_changes_without_backend_tests(self) -> None:
        feature = self._feature()

        with patch(
            "automation.validation_runner._changed_files_since_default",
            side_effect=[["app/lead_gen/jobs/routes.py"], ["src/test/regression/leadGenFlow.test.tsx"]],
        ), patch("automation.validation_runner.subprocess.run") as run_command:
            result = execute_validation_run(feature)

        self.assertEqual("failed", result.status)
        self.assertIn("backend app changes detected without matching test changes", result.detail)
        run_command.assert_not_called()

    def test_fails_when_frontend_code_changes_without_frontend_tests(self) -> None:
        feature = self._feature()

        with patch(
            "automation.validation_runner._changed_files_since_default",
            side_effect=[["tests/test_lead_gen_routes.py"], ["src/features/lead-gen/pages/LeadGenPage.tsx"]],
        ), patch("automation.validation_runner.subprocess.run") as run_command:
            result = execute_validation_run(feature)

        self.assertEqual("failed", result.status)
        self.assertIn("frontend src changes detected without matching test changes", result.detail)
        run_command.assert_not_called()

    def test_runs_validation_commands_when_code_and_tests_change_together(self) -> None:
        feature = self._feature()

        with patch(
            "automation.validation_runner._changed_files_since_default",
            side_effect=[
                ["app/lead_gen/jobs/routes.py", "tests/test_lead_gen_routes.py"],
                ["src/features/lead-gen/pages/LeadGenPage.tsx", "src/test/regression/leadGenFlow.test.tsx"],
            ],
        ), patch("automation.validation_runner.subprocess.run") as run_command:
            run_command.return_value.returncode = 0
            run_command.return_value.stdout = "ok"
            run_command.return_value.stderr = ""

            result = execute_validation_run(feature)

        self.assertEqual("done", result.status)
        self.assertEqual(4, run_command.call_count)

    def _feature(self) -> FeatureManifest:
        return FeatureManifest(
            id="job-retry-controls",
            title="Add failed job retry controls",
            status="approved",
            priority=10,
            backend_repo="/tmp/backend",
            frontend_repo="/tmp/frontend",
            backend_branch="agent/job-retry-controls-backend",
            frontend_branch="agent/job-retry-controls-frontend",
            acceptance_criteria=["Retry failed jobs"],
            api_contract=["POST /api/lead_gen/jobs/:id/retry"],
            source_file="automation/features/job_retry_controls.json",
        )


if __name__ == "__main__":
    unittest.main()
