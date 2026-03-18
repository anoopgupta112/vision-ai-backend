import subprocess

from automation.models import FeatureManifest, StageResult
from automation.git_utils import get_github_repo_slug
from automation.templates import (
    backend_cross_link_comment,
    backend_pr_body,
    backend_pr_title,
    frontend_cross_link_comment,
    frontend_pr_body,
    frontend_pr_title,
)


def plan_pull_requests(feature: FeatureManifest) -> StageResult:
    backend_repo_slug = get_github_repo_slug(feature.backend_repo)
    frontend_repo_slug = get_github_repo_slug(feature.frontend_repo)
    backend_title = backend_pr_title(feature)
    frontend_title = frontend_pr_title(feature)
    backend_body = backend_pr_body(feature).replace("\n", "\\n")
    frontend_body = frontend_pr_body(feature).replace("\n", "\\n")

    return StageResult(
        name="pull_requests",
        status="pending",
        detail=(
            f"backend: gh pr create --repo {backend_repo_slug} --head {feature.backend_branch} "
            f"--title \"{backend_title}\" --body \"{backend_body}\""
            f" | frontend: gh pr create --repo {frontend_repo_slug} --head {feature.frontend_branch} "
            f"--title \"{frontend_title}\" --body \"{frontend_body}\""
            f" | then add cross-link comments on both PRs"
        ),
    )


def execute_pull_requests(feature: FeatureManifest) -> StageResult:
    backend_repo_slug = get_github_repo_slug(feature.backend_repo)
    frontend_repo_slug = get_github_repo_slug(feature.frontend_repo)

    commands = [
        [
            "gh",
            "pr",
            "create",
            "--repo",
            backend_repo_slug,
            "--head",
            feature.backend_branch,
            "--title",
            backend_pr_title(feature),
            "--body",
            backend_pr_body(feature),
        ],
        [
            "gh",
            "pr",
            "create",
            "--repo",
            frontend_repo_slug,
            "--head",
            feature.frontend_branch,
            "--title",
            frontend_pr_title(feature),
            "--body",
            frontend_pr_body(feature),
        ],
    ]

    urls: list[str] = []
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            return StageResult(
                name="pull_requests",
                status="failed",
                detail=(completed.stderr or completed.stdout).strip() or "PR creation failed",
            )
        urls.append(completed.stdout.strip())

    if len(urls) != 2:
        return StageResult(
            name="pull_requests",
            status="failed",
            detail="PR creation output did not include both PR URLs.",
        )

    backend_url, frontend_url = urls

    comment_commands = [
        [
            "gh",
            "pr",
            "comment",
            "--repo",
            backend_repo_slug,
            backend_url,
            "--body",
            backend_cross_link_comment(frontend_url, feature),
        ],
        [
            "gh",
            "pr",
            "comment",
            "--repo",
            frontend_repo_slug,
            frontend_url,
            "--body",
            frontend_cross_link_comment(backend_url, feature),
        ],
    ]

    for command in comment_commands:
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            return StageResult(
                name="pull_requests",
                status="failed",
                detail=(completed.stderr or completed.stdout).strip() or "PR cross-link comment failed",
            )

    return StageResult(
        name="pull_requests",
        status="done",
        detail=f"Backend and frontend pull requests created and cross-linked. backend={backend_url} frontend={frontend_url}",
    )
