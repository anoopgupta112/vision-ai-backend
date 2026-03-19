from automation.models import FeatureManifest, StageResult


def backend_pr_title(feature: FeatureManifest) -> str:
    return f"feat: {feature.title} (backend)"


def frontend_pr_title(feature: FeatureManifest) -> str:
    return f"feat: {feature.title} (frontend)"


def backend_pr_body(feature: FeatureManifest, stage_results: list[StageResult]) -> str:
    acceptance = "\n".join(f"- {item}" for item in feature.acceptance_criteria)
    api_contract = "\n".join(f"- {item}" for item in feature.api_contract)
    stage_summary = _stage_summary(stage_results)
    codex_note = _codex_exhausted_note(stage_results)
    return f"""## Summary

Implements the backend portion of `{feature.id}`.

## Acceptance Criteria

{acceptance}

## API Contract

{api_contract}

## Automation Status

{stage_summary}

{codex_note}

## Notes

- Backend branch: `{feature.backend_branch}`
- Frontend branch: `{feature.frontend_branch}`
- Frontend PR should be linked after both PRs are created.
"""


def frontend_pr_body(feature: FeatureManifest, stage_results: list[StageResult]) -> str:
    acceptance = "\n".join(f"- {item}" for item in feature.acceptance_criteria)
    api_contract = "\n".join(f"- {item}" for item in feature.api_contract)
    stage_summary = _stage_summary(stage_results)
    codex_note = _codex_exhausted_note(stage_results)
    return f"""## Summary

Implements the frontend portion of `{feature.id}`.

## Acceptance Criteria

{acceptance}

## API Contract

{api_contract}

## Automation Status

{stage_summary}

{codex_note}

## Notes

- Frontend branch: `{feature.frontend_branch}`
- Backend branch: `{feature.backend_branch}`
- Backend PR should be linked after both PRs are created.
"""


def backend_cross_link_comment(frontend_pr_url: str, feature: FeatureManifest) -> str:
    return (
        f"Linked frontend PR for `{feature.id}`: {frontend_pr_url}\n\n"
        f"This backend PR is part of the coordinated delivery for `{feature.title}`."
    )


def frontend_cross_link_comment(backend_pr_url: str, feature: FeatureManifest) -> str:
    return (
        f"Linked backend PR for `{feature.id}`: {backend_pr_url}\n\n"
        f"This frontend PR is part of the coordinated delivery for `{feature.title}`."
    )


def _stage_summary(stage_results: list[StageResult]) -> str:
    return "\n".join(f"- `{stage.name}`: `{stage.status}` - {stage.detail}" for stage in stage_results)


def _codex_exhausted_note(stage_results: list[StageResult]) -> str:
    exhausted = [stage for stage in stage_results if stage.status == "exhausted"]
    if not exhausted:
        return ""

    details = "\n".join(f"- `{stage.name}`: {stage.detail}" for stage in exhausted)
    return f"""## Codex Exhausted

Codex was exhausted during automation and the PR was opened with the failure details below.

{details}
"""
