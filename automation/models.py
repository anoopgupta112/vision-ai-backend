from dataclasses import dataclass, field
from typing import List


ALLOWED_FEATURE_STATUSES = {
    "suggested",
    "approved",
    "in_progress",
    "pr_opened",
    "merged",
    "rejected",
}


@dataclass
class FeatureManifest:
    id: str
    title: str
    status: str
    priority: int
    backend_repo: str
    frontend_repo: str
    backend_branch: str
    frontend_branch: str
    acceptance_criteria: List[str] = field(default_factory=list)
    api_contract: List[str] = field(default_factory=list)
    source_file: str = ""


@dataclass
class StageResult:
    name: str
    status: str
    detail: str
