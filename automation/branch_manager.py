import subprocess

from automation.models import FeatureManifest, StageResult


def plan_branch_preparation(feature: FeatureManifest) -> StageResult:
    detail = " | ".join(
        [
            _branch_detail("backend", feature.backend_repo, feature.backend_branch),
            _branch_detail("frontend", feature.frontend_repo, feature.frontend_branch),
        ]
    )
    return StageResult(
        name="branch_preparation",
        status="pending",
        detail=detail,
    )


def execute_branch_preparation(feature: FeatureManifest) -> StageResult:
    tasks = [
        ("backend", feature.backend_repo, feature.backend_branch),
        ("frontend", feature.frontend_repo, feature.frontend_branch),
    ]

    for label, repo_path, branch in tasks:
        fetch = subprocess.run(["git", "fetch", "origin"], cwd=repo_path, capture_output=True, text=True)
        if fetch.returncode != 0:
            return StageResult(
                name="branch_preparation",
                status="failed",
                detail=f"{label} fetch failed: {(fetch.stderr or fetch.stdout).strip()}",
            )

        switch = subprocess.run(["git", "switch", branch], cwd=repo_path, capture_output=True, text=True)
        if switch.returncode != 0:
            create = subprocess.run(["git", "switch", "-c", branch], cwd=repo_path, capture_output=True, text=True)
            if create.returncode != 0:
                return StageResult(
                    name="branch_preparation",
                    status="failed",
                    detail=f"{label} branch switch/create failed: {(create.stderr or create.stdout).strip()}",
                )

    return StageResult(
        name="branch_preparation",
        status="done",
        detail="Backend and frontend branches are prepared.",
    )


def _branch_detail(label: str, repo_path: str, branch: str) -> str:
    return (
        f"{label}: git fetch origin && "
        f"(git switch {branch} || git switch -c {branch}) "
        f"(cwd={repo_path})"
    )
