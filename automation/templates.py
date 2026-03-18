from automation.models import FeatureManifest


def backend_pr_title(feature: FeatureManifest) -> str:
    return f"feat: {feature.title} (backend)"


def frontend_pr_title(feature: FeatureManifest) -> str:
    return f"feat: {feature.title} (frontend)"


def backend_pr_body(feature: FeatureManifest) -> str:
    acceptance = "\n".join(f"- {item}" for item in feature.acceptance_criteria)
    api_contract = "\n".join(f"- {item}" for item in feature.api_contract)
    return f"""## Summary

Implements the backend portion of `{feature.id}`.

## Acceptance Criteria

{acceptance}

## API Contract

{api_contract}

## Notes

- Backend branch: `{feature.backend_branch}`
- Frontend branch: `{feature.frontend_branch}`
- Frontend PR should be linked after both PRs are created.
"""


def frontend_pr_body(feature: FeatureManifest) -> str:
    acceptance = "\n".join(f"- {item}" for item in feature.acceptance_criteria)
    api_contract = "\n".join(f"- {item}" for item in feature.api_contract)
    return f"""## Summary

Implements the frontend portion of `{feature.id}`.

## Acceptance Criteria

{acceptance}

## API Contract

{api_contract}

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
