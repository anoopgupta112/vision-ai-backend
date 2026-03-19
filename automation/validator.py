from pathlib import Path
from typing import List

from automation.models import FeatureManifest


def validate_feature_manifest(feature: FeatureManifest) -> List[str]:
    issues: List[str] = []

    if not Path(feature.backend_repo).exists():
        issues.append(f"backend repo does not exist: {feature.backend_repo}")
    if not Path(feature.frontend_repo).exists():
        issues.append(f"frontend repo does not exist: {feature.frontend_repo}")
    if feature.backend_repo == feature.frontend_repo:
        issues.append("backend and frontend repos must be different")
    if not feature.acceptance_criteria:
        issues.append("acceptance_criteria must not be empty")
    if not feature.api_contract:
        issues.append("api_contract must not be empty")

    return issues
