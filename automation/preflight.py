import os
import shutil
import subprocess
from typing import Optional

from automation.models import FeatureManifest, StageResult


def run_preflight(
    feature: FeatureManifest,
    require_codex: bool = False,
    require_github: bool = False,
    require_webhook: bool = False,
) -> StageResult:
    issues: list[str] = []

    for label, repo_path in (("backend", feature.backend_repo), ("frontend", feature.frontend_repo)):
        if not os.path.isdir(repo_path):
            issues.append(f"{label} repo missing: {repo_path}")
        elif not os.path.isdir(os.path.join(repo_path, ".git")):
            issues.append(f"{label} repo is not a git checkout: {repo_path}")

    if shutil.which("git") is None:
        issues.append("git command not found")

    if require_codex:
        if shutil.which("codex") is None:
            issues.append("codex command not found")

    if require_github:
        if shutil.which("gh") is None:
            issues.append("gh command not found")

        gh_status = _run_command(["gh", "auth", "status"])
        if gh_status is not None and gh_status.returncode != 0:
            issues.append((gh_status.stderr or gh_status.stdout).strip() or "gh auth status failed")

    if require_webhook and not os.environ.get("AUTOMATION_WEBHOOK_URL", "").strip():
        issues.append("AUTOMATION_WEBHOOK_URL is not configured")

    if issues:
        return StageResult("preflight", "failed", "; ".join(issues))

    return StageResult("preflight", "done", "Preflight checks passed.")


def _run_command(command: list[str]) -> Optional[subprocess.CompletedProcess]:
    if shutil.which(command[0]) is None:
        return None
    return subprocess.run(command, capture_output=True, text=True)
