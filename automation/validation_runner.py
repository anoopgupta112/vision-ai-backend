import subprocess
from typing import List

from automation.models import FeatureManifest, StageResult


def validation_commands(feature: FeatureManifest) -> List[dict]:
    return [
        {
            "name": "backend_regression",
            "cwd": feature.backend_repo,
            "command": [".venv/bin/python", "-m", "unittest", "discover", "-s", "tests"],
        },
        {
            "name": "frontend_test",
            "cwd": feature.frontend_repo,
            "command": ["npm", "run", "test"],
        },
        {
            "name": "frontend_lint",
            "cwd": feature.frontend_repo,
            "command": ["npm", "run", "lint"],
        },
        {
            "name": "frontend_build",
            "cwd": feature.frontend_repo,
            "command": ["npm", "run", "build"],
        },
    ]


def _changed_files_since_default(repo_path: str) -> List[str]:
    base_refs = ["origin/main", "main", "origin/master", "master"]

    for base_ref in base_refs:
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", base_ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            diff = subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if diff.returncode == 0:
                return [line for line in diff.stdout.splitlines() if line.strip()]

    fallback = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if fallback.returncode == 0:
        return [line for line in fallback.stdout.splitlines() if line.strip()]

    return []


def _has_prefix(paths: List[str], prefix: str) -> bool:
    return any(path.startswith(prefix) for path in paths)


def plan_validation_run(feature: FeatureManifest) -> StageResult:
    command_strings = [
        f"{item['name']}: {' '.join(item['command'])} (cwd={item['cwd']})"
        for item in validation_commands(feature)
    ]
    return StageResult(
        name="validation",
        status="pending",
        detail="Validation runner ready. Commands: " + " | ".join(command_strings),
    )


def execute_validation_run(feature: FeatureManifest) -> StageResult:
    backend_changed_files = _changed_files_since_default(feature.backend_repo)
    frontend_changed_files = _changed_files_since_default(feature.frontend_repo)

    if _has_prefix(backend_changed_files, "app/") and not _has_prefix(backend_changed_files, "tests/"):
        return StageResult(
            name="validation",
            status="failed",
            detail="backend app changes detected without matching test changes",
        )

    if _has_prefix(frontend_changed_files, "src/") and not _has_prefix(frontend_changed_files, "src/test/"):
        return StageResult(
            name="validation",
            status="failed",
            detail="frontend src changes detected without matching test changes",
        )

    for item in validation_commands(feature):
        completed = subprocess.run(
            item["command"],
            cwd=item["cwd"],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            detail = stderr or stdout or f"{item['name']} failed without output"
            return StageResult(
                name="validation",
                status="failed",
                detail=f"{item['name']} failed: {detail}",
            )

    return StageResult(
        name="validation",
        status="done",
        detail="Backend and frontend validation commands completed successfully.",
    )
