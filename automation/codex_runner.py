import subprocess

from automation.models import FeatureManifest, StageResult
from automation.prompt_builder import backend_prompt, frontend_prompt


def plan_backend_codex_run(feature: FeatureManifest, extra_context: str = "", attempt: int = 1) -> StageResult:
    prompt = backend_prompt(feature, extra_context=extra_context).replace("\n", "\\n")
    return StageResult(
        name=f"backend_codex_attempt_{attempt}",
        status="pending",
        detail=(
            f"codex exec --full-auto -C {feature.backend_repo} "
            f"'{prompt}'"
        ),
    )


def plan_frontend_codex_run(feature: FeatureManifest, extra_context: str = "", attempt: int = 1) -> StageResult:
    prompt = frontend_prompt(feature, extra_context=extra_context).replace("\n", "\\n")
    return StageResult(
        name=f"frontend_codex_attempt_{attempt}",
        status="pending",
        detail=(
            f"codex exec --full-auto -C {feature.frontend_repo} "
            f"'{prompt}'"
        ),
    )


def execute_backend_codex_run(feature: FeatureManifest, extra_context: str = "", attempt: int = 1) -> StageResult:
    return _execute_codex(
        stage_name=f"backend_codex_attempt_{attempt}",
        repo_path=feature.backend_repo,
        prompt=backend_prompt(feature, extra_context=extra_context),
    )


def execute_frontend_codex_run(feature: FeatureManifest, extra_context: str = "", attempt: int = 1) -> StageResult:
    return _execute_codex(
        stage_name=f"frontend_codex_attempt_{attempt}",
        repo_path=feature.frontend_repo,
        prompt=frontend_prompt(feature, extra_context=extra_context),
    )


def _execute_codex(stage_name: str, repo_path: str, prompt: str) -> StageResult:
    try:
        completed = subprocess.run(
            ["codex", "exec", "--full-auto", "-C", repo_path, prompt],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return StageResult(
            name=stage_name,
            status="failed",
            detail="codex command not found in execution environment",
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"{stage_name} failed"
        if _is_codex_exhausted(detail):
            return StageResult(
                name=stage_name,
                status="exhausted",
                detail=detail,
            )
        return StageResult(
            name=stage_name,
            status="failed",
            detail=detail,
        )

    return StageResult(
        name=stage_name,
        status="done",
        detail="Codex execution completed.",
    )


def _is_codex_exhausted(detail: str) -> bool:
    normalized = detail.lower()
    return any(
        pattern in normalized
        for pattern in (
            "rate limit",
            "quota",
            "insufficient credits",
            "usage limit",
            "exhaust",
            "too many requests",
        )
    )
