import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

from automation.feature_store import FEATURES_DIR, load_feature_manifests, save_feature_manifest


BACKEND_DEFAULT = "/Users/anoopchandra/repositories/main_dashboard"
FRONTEND_DEFAULT = "/Users/anoopchandra/repositories/main_dashboard_frontend"
DISCOVERY_SKILL_FILE = Path(__file__).resolve().parent / "discovery_skill.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover suggested features from backend and frontend repos")
    parser.add_argument("--backend-repo", type=Path, default=Path(BACKEND_DEFAULT))
    parser.add_argument("--frontend-repo", type=Path, default=Path(FRONTEND_DEFAULT))
    parser.add_argument("--features-dir", type=Path, default=FEATURES_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def load_discovery_skill(skill_file: Optional[Path] = None) -> Dict[str, Any]:
    skill_file = skill_file or DISCOVERY_SKILL_FILE
    if not skill_file.exists():
        return {
            "project_name": "",
            "project_summary": "",
            "discovery_goals": [],
            "backend_context": [],
            "frontend_context": [],
            "feature_templates": [],
        }
    return json.loads(skill_file.read_text())


# Directories to skip during repo scanning (they are irrelevant to feature discovery
# and would otherwise add thousands of files and several seconds of scan time).
_SKIP_DIRS = frozenset({
    ".venv", "venv", "env", ".env",
    "node_modules", ".git",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", ".svelte-kit",
    "coverage", ".coverage",
    "static",  # compiled static assets
})


def _iter_repo_files(repo: Path):
    """Yield all files in *repo* that aren't inside a skipped directory."""
    for path in repo.rglob("*"):
        # Check every path component — skip if any part matches _SKIP_DIRS
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path



def discover_features(
    backend_repo: Path,
    frontend_repo: Path,
    features_dir: Path = FEATURES_DIR,
    write: bool = False,
    include_exploratory: bool = False,
    discovery_skill_file: Optional[Path] = None,
) -> list[dict[str, Any]]:
    backend_files = {path.relative_to(backend_repo).as_posix() for path in _iter_repo_files(backend_repo)}
    frontend_files = {path.relative_to(frontend_repo).as_posix() for path in _iter_repo_files(frontend_repo)}
    backend_text = _read_repo_text(backend_repo)
    frontend_text = _read_repo_text(frontend_repo)
    existing_ids = {manifest.id for manifest in load_feature_manifests(features_dir)}
    discovery_skill = load_discovery_skill(discovery_skill_file)

    suggestions = [
        suggestion
        for suggestion in _build_suggestions(
            backend_files,
            frontend_files,
            backend_text,
            frontend_text,
            backend_repo,
            frontend_repo,
            discovery_skill,
            include_exploratory=include_exploratory,
        )
        if suggestion["id"] not in existing_ids
    ]

    if write:
        for suggestion in suggestions:
            save_feature_manifest(suggestion, features_dir)

    return suggestions


def _build_suggestions(
    backend_files: set[str],
    frontend_files: set[str],
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
    discovery_skill: Dict[str, Any],
    include_exploratory: bool,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    for template in discovery_skill.get("feature_templates", []):
        if template.get("tier") == "exploratory" and not include_exploratory:
            continue
        is_exploratory = template.get("tier") == "exploratory"
        required_backend = set(template.get("required_backend_files", []))
        required_frontend = set(template.get("required_frontend_files", []))
        if not required_backend.issubset(backend_files):
            continue
        # Exploratory templates are aspirational — skip frontend file check so
        # they surface even when the frontend repo isn't linked or the files
        # don't exist yet.
        if not is_exploratory and not required_frontend.issubset(frontend_files):
            continue

        suggestions.append(
            _feature_manifest(
                feature_id=template["id"],
                title=template["title"],
                priority=int(template.get("priority", 100)),
                acceptance_criteria=template.get("acceptance_criteria", []),
                api_contract=template.get("api_contract", []),
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category=template.get("category", "product_workflow"),
            )
        )

    suggestions.extend(
        _field_driven_feature_suggestions(
            backend_text=backend_text,
            frontend_text=frontend_text,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
        )
    )
    suggestions.extend(
        _website_improvement_suggestions(
            backend_text=backend_text,
            frontend_text=frontend_text,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
            include_exploratory=include_exploratory,
        )
    )
    suggestions.extend(
        _analyzer_feature_suggestions(
            backend_text=backend_text,
            frontend_text=frontend_text,
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
        )
    )
    return _dedupe_projects(suggestions)




def _dedupe_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for project in projects:
        project_id = project.get("id")
        if not project_id or project_id in seen:
            continue
        seen.add(project_id)
        result.append(project)
    return sorted(result, key=lambda item: (item.get("priority", 100), item.get("id", "")))


def _feature_manifest(
    feature_id: str,
    title: str,
    priority: int,
    acceptance_criteria: list[str],
    api_contract: list[str],
    backend_repo: Path,
    frontend_repo: Path,
    category: str = "product_workflow",
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "title": title,
        "status": "suggested",
        "priority": priority,
        "category": category,
        "backend_repo": str(backend_repo),
        "frontend_repo": str(frontend_repo),
        "branches": {
            "backend": f"agent/{feature_id}-backend",
            "frontend": f"agent/{feature_id}-frontend",
        },
        "acceptance_criteria": acceptance_criteria,
        "api_contract": api_contract,
    }


def _read_repo_text(repo: Path) -> str:
    chunks: list[str] = []
    for path in _iter_repo_files(repo):
        if path.suffix.lower() not in {".py", ".tsx", ".ts", ".js", ".jsx", ".json", ".md"}:
            continue
        try:
            chunks.append(path.read_text(errors="ignore"))
        except Exception:
            continue
    return "\n".join(chunks)


def _field_driven_feature_suggestions(
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
) -> list[dict[str, Any]]:
    combined = f"{backend_text}\n{frontend_text}".lower()
    backend_lower = backend_text.lower()
    suggestions: list[dict[str, Any]] = []
    has_lead_scope = (
        "lead_gen" in backend_repo.as_posix().lower()
        or "lead_gen" in backend_lower
        or "lead_" in backend_lower
        or "phone" in backend_lower
        or "website" in backend_lower
        or "address" in backend_lower
    )

    if not has_lead_scope:
        return suggestions

    if "website" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="lead-website-actions",
                title="Add lead website preview and quick actions",
                priority=85,
                acceptance_criteria=[
                    "Users can open or preview lead websites directly from lead workflows",
                    "Website-related actions are accessible from lead rows or lead details",
                    "Lead and export workflows remain green",
                ],
                api_contract=["GET /api/lead_gen/leads/job/:id"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="data_features",
            )
        )

    if "phone" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="lead-phone-actions",
                title="Add phone actions and outreach shortcuts",
                priority=86,
                acceptance_criteria=[
                    "Users can trigger direct phone-oriented actions from lead records",
                    "Phone values are formatted and handled safely in the UI",
                    "Lead workflows remain green",
                ],
                api_contract=["GET /api/lead_gen/leads/job/:id"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="data_features",
            )
        )

    if "address" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="lead-address-map-actions",
                title="Add address map and location quick actions",
                priority=87,
                acceptance_criteria=[
                    "Users can open lead addresses in maps or location actions",
                    "Address visibility is improved in lead workflows",
                    "Lead workflows remain green",
                ],
                api_contract=["GET /api/lead_gen/leads/job/:id"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="data_features",
            )
        )

    if "phone" in combined or "website" in combined or "address" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="ai-lead-contact-assistant",
                title="Add AI contact assistant for lead records",
                priority=88,
                acceptance_criteria=[
                    "AI suggests practical next actions from lead contact fields",
                    "Suggestions stay tied to real lead workflows like call, visit site, or review address quality",
                    "AI assistance remains optional and non-blocking",
                ],
                api_contract=[
                    "GET /api/lead_gen/leads/job/:id",
                    "POST /api/lead_gen/leads/job/:id/contact-assistant",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="ai_support",
            )
        )

    return suggestions


def _website_improvement_suggestions(
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
    include_exploratory: bool,
) -> list[dict[str, Any]]:
    combined = f"{backend_text}\n{frontend_text}".lower()
    backend_lower = backend_text.lower()
    suggestions: list[dict[str, Any]] = []
    has_payment_scope = "payment" in backend_lower or "/api/payments" in backend_lower
    is_root_dashboard = backend_repo.resolve() == Path(BACKEND_DEFAULT).resolve()

    if has_payment_scope and "payment" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="payment-page-upgrade",
                title="Improve payment page trust and conversion flow",
                priority=95,
                acceptance_criteria=[
                    "Payment page communicates package value and trust signals more clearly",
                    "Existing payment creation flow remains intact",
                    "Payment regression suites remain green",
                ],
                api_contract=[
                    "GET /api/payments/packages",
                    "POST /api/payments/create-order",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="website_improvement",
            )
        )

    if include_exploratory and is_root_dashboard and ("login" in combined or "dashboard" in combined):
        suggestions.append(
            _feature_manifest(
                feature_id="landing-page-conversion-upgrade",
                title="Improve landing page and entry conversion experience",
                priority=96,
                acceptance_criteria=[
                    "Landing and entry surfaces communicate product value more clearly",
                    "Existing auth and dashboard routes continue to work",
                    "Frontend regression suites remain green",
                ],
                api_contract=["GET /", "GET /health"],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="website_improvement",
            )
        )

    return suggestions


def _analyzer_feature_suggestions(
    backend_text: str,
    frontend_text: str,
    backend_repo: Path,
    frontend_repo: Path,
) -> list[dict[str, Any]]:
    combined = f"{backend_text}\n{frontend_text}".lower()
    backend_lower = backend_text.lower()
    repo_lower = backend_repo.as_posix().lower()
    suggestions: list[dict[str, Any]] = []
    is_analyzer_scope = (
        "analyzer" in repo_lower
        or "/api/analyzer" in backend_lower
        or "match_from_pdfs" in backend_lower
        or "github_questions" in backend_lower
    )

    if not is_analyzer_scope:
        return suggestions

    if "forms" in combined and "submission" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="analyzer-submission-review-workbench",
                title="Add analyzer submission review workbench",
                priority=55,
                acceptance_criteria=[
                    "Users can review analyzer form submissions with clearer submission status and metadata",
                    "Review flow supports opening submission details without leaving the analyzer workflow",
                    "Analyzer form and submission flows remain green",
                ],
                api_contract=[
                    "GET /api/analyzer/forms",
                    "GET /api/analyzer/forms/:form_id/submissions",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="product_workflow",
            )
        )

    if "match_report" in combined or "evaluate_resume_against_jd" in combined or "jd" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="analyzer-score-breakdown",
                title="Add analyzer score breakdown and recruiter summary",
                priority=56,
                acceptance_criteria=[
                    "Analysis results expose a clearer score breakdown for recruiters",
                    "Users can understand why a resume matched or missed the job description",
                    "Analyzer matching flows remain green",
                ],
                api_contract=[
                    "POST /api/analyzer/forms/:form_id/analyze",
                    "POST /api/analyzer/v1/match_from_pdfs",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="ai_support",
            )
        )

    if "github" in combined and "questions" in combined:
        suggestions.append(
            _feature_manifest(
                feature_id="analyzer-github-question-review",
                title="Add GitHub question review and export for analyzer",
                priority=57,
                acceptance_criteria=[
                    "Users can review generated GitHub questions in a structured analyzer flow",
                    "Question sets can be exported or copied for interviewer use",
                    "Analyzer GitHub question generation remains green",
                ],
                api_contract=[
                    "POST /api/analyzer/v1/github_questions",
                    "POST /api/analyzer/v1/match_from_pdfs",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
                category="product_workflow",
            )
        )

    return suggestions


def main() -> int:
    args = parse_args()
    suggestions = discover_features(
        backend_repo=args.backend_repo,
        frontend_repo=args.frontend_repo,
        features_dir=args.features_dir,
        write=args.write,
        include_exploratory=False,
    )
    print(json.dumps({"discovered_features": suggestions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
