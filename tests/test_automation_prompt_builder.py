import unittest

from automation.models import FeatureManifest
from automation.prompt_builder import backend_prompt, frontend_prompt


class PromptBuilderTests(unittest.TestCase):
    def test_backend_prompt_requires_matching_backend_tests(self) -> None:
        prompt = backend_prompt(self._feature())

        self.assertIn("Add or update backend tests for every API route", prompt)
        self.assertIn("Do not leave backend app changes without matching backend test changes.", prompt)

    def test_frontend_prompt_requires_matching_frontend_tests(self) -> None:
        prompt = frontend_prompt(self._feature())

        self.assertIn("Add or update frontend tests for every page, component, API integration, or user flow", prompt)
        self.assertIn("Do not leave frontend src changes without matching frontend test changes.", prompt)

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
