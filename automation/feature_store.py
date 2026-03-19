import json
import os
import re
from pathlib import Path
from typing import Any, List

from automation.models import ALLOWED_FEATURE_STATUSES, FeatureManifest


FEATURES_DIR = Path(__file__).resolve().parent / "features"


def load_feature_manifests(features_dir: Path = FEATURES_DIR) -> List[FeatureManifest]:
    manifests: List[FeatureManifest] = []

    if not features_dir.exists():
        return manifests

    for path in sorted(features_dir.glob("*.json")):
        data = json.loads(path.read_text())
        manifests.append(_build_manifest(data, path))

    return manifests


def _build_manifest(data: dict, path: Path) -> FeatureManifest:
    status = data.get("status", "").strip()
    if status not in ALLOWED_FEATURE_STATUSES:
        raise ValueError(
            f"{path}: invalid status '{status}'. "
            f"Allowed values: {sorted(ALLOWED_FEATURE_STATUSES)}"
        )

    branches = data.get("branches") or {}
    acceptance_criteria = data.get("acceptance_criteria") or []
    api_contract = data.get("api_contract") or []

    return FeatureManifest(
        id=_require_string(data, "id", path),
        title=_require_string(data, "title", path),
        status=status,
        priority=int(data.get("priority", 100)),
        backend_repo=_resolve_path_template(_require_string(data, "backend_repo", path)),
        frontend_repo=_resolve_path_template(_require_string(data, "frontend_repo", path)),
        backend_branch=_require_string(branches, "backend", path, scope="branches"),
        frontend_branch=_require_string(branches, "frontend", path, scope="branches"),
        acceptance_criteria=_require_string_list(acceptance_criteria, path, "acceptance_criteria"),
        api_contract=_require_string_list(api_contract, path, "api_contract"),
        source_file=str(path),
    )


def pick_next_approved_feature(manifests: List[FeatureManifest]) -> FeatureManifest:
    approved = [manifest for manifest in manifests if manifest.status == "approved"]
    if not approved:
        raise ValueError("No approved feature manifests found.")

    approved.sort(key=lambda item: (item.priority, item.id))
    return approved[0]


def pick_next_suggested_feature(manifests: List[FeatureManifest]) -> FeatureManifest:
    suggested = [manifest for manifest in manifests if manifest.status == "suggested"]
    if not suggested:
        raise ValueError("No suggested feature manifests found.")

    suggested.sort(key=lambda item: (item.priority, item.id))
    return suggested[0]


def save_feature_manifest(data: dict[str, Any], features_dir: Path = FEATURES_DIR) -> Path:
    features_dir.mkdir(parents=True, exist_ok=True)
    path = features_dir / f"{_slugify(data['id'])}.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def update_feature_manifest_status(feature: FeatureManifest, status: str) -> Path:
    if status not in ALLOWED_FEATURE_STATUSES:
        raise ValueError(f"invalid status '{status}'. Allowed values: {sorted(ALLOWED_FEATURE_STATUSES)}")

    path = Path(feature.source_file)
    data = json.loads(path.read_text())
    data["status"] = status
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def _require_string(data: dict, key: str, path: Path, scope: str = "root") -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: missing non-empty string '{key}' in {scope}")
    return value.strip()


def _require_string_list(values: list, path: Path, key: str) -> List[str]:
    if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError(f"{path}: '{key}' must be a list of non-empty strings")
    return [item.strip() for item in values]


def _resolve_path_template(value: str) -> str:
    pattern = re.compile(r"\$\{([^}:]+)(:-([^}]*))?\}")

    def replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        default = match.group(3)
        return os.environ.get(env_name, default if default is not None else match.group(0))

    return pattern.sub(replace, value)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError("feature id must contain at least one alphanumeric character")
    return slug
