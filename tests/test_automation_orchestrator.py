import io
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from automation.models import FeatureManifest, StageResult
from automation import orchestrator


class OrchestratorTests(unittest.TestCase):
    def test_stops_before_prs_when_validation_fails(self) -> None:
        feature = self._feature()
        args = self._args()

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[feature]), \
            patch("automation.orchestrator.pick_next_approved_feature", return_value=feature), \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "done", "ok")), \
            patch("automation.orchestrator.update_feature_manifest_status"), \
            patch("automation.orchestrator.execute_branch_preparation", return_value=StageResult("branch_preparation", "done", "ok")), \
            patch("automation.orchestrator.execute_backend_codex_run", return_value=StageResult("backend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_frontend_codex_run", return_value=StageResult("frontend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_validation_run", return_value=StageResult("validation", "failed", "tests failed")), \
            patch("automation.orchestrator.execute_branch_push"), \
            patch("automation.orchestrator.execute_pull_requests") as execute_pull_requests:
            exit_code = orchestrator.main()

        self.assertEqual(1, exit_code)
        execute_pull_requests.assert_not_called()

    def test_returns_zero_when_no_approved_feature_exists(self) -> None:
        args = self._args()

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[]), \
            patch("automation.orchestrator.pick_next_approved_feature", side_effect=ValueError("No approved feature manifests found.")):
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = orchestrator.main()

        self.assertEqual(0, exit_code)
        self.assertIn('"selected_feature": null', output.getvalue())

    def test_auto_approves_suggested_feature_when_enabled(self) -> None:
        feature = self._feature(status="suggested")
        args = self._args(auto_approve=True, execute_prs=False)

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", side_effect=[[feature], [self._feature()]]), \
            patch("automation.orchestrator.pick_next_approved_feature", side_effect=[ValueError("No approved feature manifests found."), self._feature()]), \
            patch("automation.orchestrator.pick_next_suggested_feature", return_value=feature), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "done", "ok")), \
            patch("automation.orchestrator.update_feature_manifest_status") as update_status, \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.execute_branch_preparation", return_value=StageResult("branch_preparation", "done", "ok")), \
            patch("automation.orchestrator.execute_backend_codex_run", return_value=StageResult("backend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_frontend_codex_run", return_value=StageResult("frontend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_validation_run", return_value=StageResult("validation", "done", "ok")), \
            patch("automation.orchestrator.plan_branch_push", return_value=StageResult("branch_push", "pending", "planned")), \
            patch("automation.orchestrator.plan_pull_requests", return_value=StageResult("pull_requests", "pending", "planned")):
            exit_code = orchestrator.main()

        self.assertEqual(0, exit_code)
        update_status.assert_any_call(feature, "approved")

    def test_force_prs_continues_after_validation_failure(self) -> None:
        feature = self._feature()
        args = self._args(execute_prs=True, force_prs=True)

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[feature]), \
            patch("automation.orchestrator.pick_next_approved_feature", return_value=feature), \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "done", "ok")), \
            patch("automation.orchestrator.update_feature_manifest_status"), \
            patch("automation.orchestrator.execute_branch_preparation", return_value=StageResult("branch_preparation", "done", "ok")), \
            patch("automation.orchestrator.execute_backend_codex_run", return_value=StageResult("backend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_frontend_codex_run", return_value=StageResult("frontend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_validation_run", return_value=StageResult("validation", "failed", "tests failed")), \
            patch("automation.orchestrator.plan_branch_push", return_value=StageResult("branch_push", "pending", "planned")), \
            patch("automation.orchestrator.execute_pull_requests", return_value=StageResult("pull_requests", "done", "opened")) as execute_pull_requests:
            exit_code = orchestrator.main()

        self.assertEqual(1, exit_code)
        execute_pull_requests.assert_called_once()

    def test_retries_validation_failures_before_succeeding(self) -> None:
        feature = self._feature()
        args = self._args(execute_prs=False)
        args.dry_run = True

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[feature]), \
            patch("automation.orchestrator.pick_next_approved_feature", return_value=feature), \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "done", "ok")), \
            patch("automation.orchestrator.update_feature_manifest_status"), \
            patch("automation.orchestrator.execute_branch_preparation", return_value=StageResult("branch_preparation", "done", "ok")), \
            patch("automation.orchestrator.execute_backend_codex_run", return_value=StageResult("backend_codex", "done", "ok")) as backend_run, \
            patch("automation.orchestrator.execute_frontend_codex_run", return_value=StageResult("frontend_codex", "done", "ok")) as frontend_run, \
            patch(
                "automation.orchestrator.execute_validation_run",
                side_effect=[StageResult("validation", "failed", "tests failed"), StageResult("validation", "done", "ok")],
            ), \
            patch("automation.orchestrator.plan_branch_push", return_value=StageResult("branch_push", "pending", "planned")), \
            patch("automation.orchestrator.plan_pull_requests", return_value=StageResult("pull_requests", "pending", "planned")):
            exit_code = orchestrator.main()

        self.assertEqual(0, exit_code)
        self.assertEqual(2, backend_run.call_count)
        self.assertEqual(2, frontend_run.call_count)

    def test_stops_when_preflight_fails(self) -> None:
        feature = self._feature()
        args = self._args()

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[feature]), \
            patch("automation.orchestrator.pick_next_approved_feature", return_value=feature), \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "failed", "missing auth")), \
            patch("automation.orchestrator.update_feature_manifest_status"), \
            patch("automation.orchestrator.execute_branch_preparation") as execute_branch_preparation:
            exit_code = orchestrator.main()

        self.assertEqual(1, exit_code)
        execute_branch_preparation.assert_not_called()

    def test_runs_explicit_feature_id_without_global_pick(self) -> None:
        feature = self._feature()
        other_feature = self._feature()
        other_feature.id = "other-approved-feature"
        args = self._args(execute_prs=False)
        args.feature_id = "job-retry-controls"
        args.dry_run = True

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[other_feature, feature]), \
            patch("automation.orchestrator.find_feature_by_id", return_value=feature) as find_feature_by_id, \
            patch("automation.orchestrator.pick_next_approved_feature") as pick_next_approved_feature, \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "done", "ok")), \
            patch("automation.orchestrator.update_feature_manifest_status"), \
            patch("automation.orchestrator.execute_branch_preparation", return_value=StageResult("branch_preparation", "done", "ok")), \
            patch("automation.orchestrator.execute_backend_codex_run", return_value=StageResult("backend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_frontend_codex_run", return_value=StageResult("frontend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_validation_run", return_value=StageResult("validation", "done", "ok")), \
            patch("automation.orchestrator.plan_branch_push", return_value=StageResult("branch_push", "pending", "planned")), \
            patch("automation.orchestrator.plan_pull_requests", return_value=StageResult("pull_requests", "pending", "planned")):
            exit_code = orchestrator.main()

        self.assertEqual(0, exit_code)
        find_feature_by_id.assert_called_once()
        pick_next_approved_feature.assert_not_called()

    def test_appends_stage_results_while_running(self) -> None:
        feature = self._feature()
        args = self._args(execute_prs=False)

        with patch("automation.orchestrator.parse_args", return_value=args), \
            patch("automation.orchestrator.load_feature_manifests", return_value=[feature]), \
            patch("automation.orchestrator.pick_next_approved_feature", return_value=feature), \
            patch("automation.orchestrator.validate_feature_manifest", return_value=[]), \
            patch("automation.orchestrator.run_preflight", return_value=StageResult("preflight", "done", "ok")), \
            patch("automation.orchestrator.mark_feature_in_progress"), \
            patch("automation.orchestrator.set_feature_status") as set_feature_status, \
            patch("automation.orchestrator.append_stage_result") as append_stage_result, \
            patch("automation.orchestrator.update_feature_manifest_status"), \
            patch("automation.orchestrator.execute_branch_preparation", return_value=StageResult("branch_preparation", "done", "ok")), \
            patch("automation.orchestrator.execute_backend_codex_run", return_value=StageResult("backend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_frontend_codex_run", return_value=StageResult("frontend_codex", "done", "ok")), \
            patch("automation.orchestrator.execute_validation_run", return_value=StageResult("validation", "done", "ok")), \
            patch("automation.orchestrator.plan_branch_push", return_value=StageResult("branch_push", "pending", "planned")), \
            patch("automation.orchestrator.plan_pull_requests", return_value=StageResult("pull_requests", "pending", "planned")):
            exit_code = orchestrator.main()

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(append_stage_result.call_count, 5)
        set_feature_status.assert_called()

    def _args(self, auto_approve: bool = False, execute_prs: bool = True, force_prs: bool = False) -> Namespace:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        return Namespace(
            features_dir=root / "features",
            state_file=root / "state.json",
            backend_repo=root / "backend",
            frontend_repo=root / "frontend",
            dry_run=False,
            discover=False,
            auto_approve=auto_approve,
            force_prs=force_prs,
            max_retries=3,
            execute_pushes=False,
            webhook_url="",
            execute_branches=True,
            execute_codex=True,
            execute_validation=True,
            execute_prs=execute_prs,
            feature_id="",
        )

    def _feature(self, status: str = "approved") -> FeatureManifest:
        return FeatureManifest(
            id="job-retry-controls",
            title="Add failed job retry controls",
            status=status,
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
