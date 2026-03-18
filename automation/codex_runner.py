import subprocess

from automation.models import FeatureManifest, StageResult
from automation.prompt_builder import backend_prompt, frontend_prompt


def plan_backend_codex_run(feature: FeatureManifest) -> StageResult:
    prompt = backend_prompt(feature).replace("\n", "\\n")
    return StageResult(
        name="backend_codex",
        status="pending",
        detail=(
            f"codex exec --full-auto -C {feature.backend_repo} "
            f"'{prompt}'"
        ),
    )


def plan_frontend_codex_run(feature: FeatureManifest) -> StageResult:
    prompt = frontend_prompt(feature).replace("\n", "\\n")
    return StageResult(
        name="frontend_codex",
        status="pending",
        detail=(
            f"codex exec --full-auto -C {feature.frontend_repo} "
            f"'{prompt}'"
        ),
    )


def execute_backend_codex_run(feature: FeatureManifest) -> StageResult:
    return _execute_codex(
        stage_name="backend_codex",
        repo_path=feature.backend_repo,
        prompt=backend_prompt(feature),
    )


def execute_frontend_codex_run(feature: FeatureManifest) -> StageResult:
    return _execute_codex(
        stage_name="frontend_codex",
        repo_path=feature.frontend_repo,
        prompt=frontend_prompt(feature),
    )


def _execute_codex(stage_name: str, repo_path: str, prompt: str) -> StageResult:
    completed = subprocess.run(
        ["codex", "exec", "--full-auto", "-C", repo_path, prompt],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return StageResult(
            name=stage_name,
            status="failed",
            detail=(completed.stderr or completed.stdout).strip() or f"{stage_name} failed",
        )

    return StageResult(
        name=stage_name,
        status="done",
        detail="Codex execution completed.",
    )
