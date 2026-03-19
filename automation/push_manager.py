from automation.git_utils import (
    commit_all_if_dirty,
    create_empty_commit,
    has_commits_ahead_of_default,
    push_branch,
)
from automation.models import FeatureManifest, StageResult


def plan_branch_push(feature: FeatureManifest) -> StageResult:
    return StageResult(
        name="branch_push",
        status="pending",
        detail=(
            f"backend: commit dirty changes if needed and push {feature.backend_branch} | "
            f"frontend: commit dirty changes if needed and push {feature.frontend_branch}"
        ),
    )


def execute_branch_push(feature: FeatureManifest, report_only: bool = False) -> StageResult:
    tasks = [
        ("backend", feature.backend_repo, feature.backend_branch),
        ("frontend", feature.frontend_repo, feature.frontend_branch),
    ]

    details: list[str] = []
    for label, repo_path, branch in tasks:
        commit_all_if_dirty(repo_path, f"chore: automation update for {feature.id} ({label})")

        if not has_commits_ahead_of_default(repo_path, branch):
            commit_message = (
                f"chore: automation report for {feature.id} ({label})"
                if report_only
                else f"chore: bootstrap automation branch for {feature.id} ({label})"
            )
            create_empty_commit(repo_path, commit_message)

        push_output = push_branch(repo_path, branch)
        details.append(f"{label} pushed {branch}: {push_output}")

    return StageResult(
        name="branch_push",
        status="done",
        detail=" | ".join(details),
    )
