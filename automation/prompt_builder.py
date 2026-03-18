from automation.models import FeatureManifest


def backend_prompt(feature: FeatureManifest) -> str:
    return _build_prompt(
        repo_role="backend",
        repo_path=feature.backend_repo,
        branch=feature.backend_branch,
        feature=feature,
        repo_specific_tasks=[
            "Write or update failing backend tests first.",
            "Implement only the backend portion of the feature.",
            "Preserve all existing behavior covered by regression tests.",
            "Run the backend regression suite before finishing.",
            "Commit your changes once tests pass.",
            "Prepare a backend PR title and summary.",
        ],
    )


def frontend_prompt(feature: FeatureManifest) -> str:
    return _build_prompt(
        repo_role="frontend",
        repo_path=feature.frontend_repo,
        branch=feature.frontend_branch,
        feature=feature,
        repo_specific_tasks=[
            "Write or update failing frontend tests first.",
            "Implement only the frontend portion of the feature.",
            "Follow the shared API contract and acceptance criteria.",
            "Run frontend test, lint, and build checks before finishing.",
            "Commit your changes once checks pass.",
            "Prepare a frontend PR title and summary.",
        ],
    )


def _build_prompt(
    repo_role: str,
    repo_path: str,
    branch: str,
    feature: FeatureManifest,
    repo_specific_tasks: list[str],
) -> str:
    acceptance = "\n".join(f"- {item}" for item in feature.acceptance_criteria)
    api_contract = "\n".join(f"- {item}" for item in feature.api_contract)
    tasks = "\n".join(f"- {item}" for item in repo_specific_tasks)

    return f"""You are implementing the {repo_role} side of an approved feature.

Feature ID: {feature.id}
Feature Title: {feature.title}
Repository Path: {repo_path}
Target Branch: {branch}

Acceptance Criteria:
{acceptance}

API Contract:
{api_contract}

Your Tasks:
{tasks}

Constraints:
- Do not merge.
- Do not skip tests.
- Keep changes scoped to this repository.
- Preserve existing regression behavior.
- If the feature is ambiguous, stop and report the ambiguity.
"""
