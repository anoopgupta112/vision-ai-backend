import argparse
import json
from pathlib import Path
from typing import Any

from automation.feature_store import FEATURES_DIR, load_feature_manifests, save_feature_manifest


BACKEND_DEFAULT = "/Users/anoopchandra/repositories/main_dashboard"
FRONTEND_DEFAULT = "/Users/anoopchandra/repositories/main_dashboard_frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover suggested features from backend and frontend repos")
    parser.add_argument("--backend-repo", type=Path, default=Path(BACKEND_DEFAULT))
    parser.add_argument("--frontend-repo", type=Path, default=Path(FRONTEND_DEFAULT))
    parser.add_argument("--features-dir", type=Path, default=FEATURES_DIR)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def discover_features(
    backend_repo: Path,
    frontend_repo: Path,
    features_dir: Path = FEATURES_DIR,
    write: bool = False,
) -> list[dict[str, Any]]:
    backend_files = {path.relative_to(backend_repo).as_posix() for path in backend_repo.rglob("*") if path.is_file()}
    frontend_files = {path.relative_to(frontend_repo).as_posix() for path in frontend_repo.rglob("*") if path.is_file()}
    existing_ids = {manifest.id for manifest in load_feature_manifests(features_dir)}

    suggestions = [
        suggestion
        for suggestion in _build_suggestions(backend_files, frontend_files, backend_repo, frontend_repo)
        if suggestion["id"] not in existing_ids
    ]

    if write:
        for suggestion in suggestions:
            save_feature_manifest(suggestion, features_dir)

    return suggestions


def _build_suggestions(
    backend_files: set[str],
    frontend_files: set[str],
    backend_repo: Path,
    frontend_repo: Path,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    if {
        "app/lead_gen/jobs/routes.py",
        "app/admin/views.py",
    }.issubset(backend_files) and {
        "src/features/lead-gen/components/JobsList.tsx",
        "src/features/admin-dashboard/pages/AdminPage.tsx",
    }.issubset(frontend_files):
        suggestions.append(
            _feature_manifest(
                feature_id="job-retry-controls",
                title="Add failed job retry controls",
                priority=30,
                acceptance_criteria=[
                    "Users can retry failed lead generation jobs from the main jobs list",
                    "Admins can trigger a retry for failed jobs from the admin dashboard",
                    "Retry eligibility is enforced so completed or running jobs cannot be retried",
                    "Backend and frontend regression suites remain green",
                ],
                api_contract=[
                    "POST /api/lead_gen/jobs/:id/retry",
                    "POST /api/admin/jobs/:id/retry",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
            )
        )

    if {
        "app/payments/routes.py",
        "app/lead_gen/credits/routes.py",
    }.issubset(backend_files) and {
        "src/features/lead-gen/pages/PaymentHistoryPage.tsx",
        "src/features/lead-gen/api/paymentsApi.ts",
    }.issubset(frontend_files):
        suggestions.append(
            _feature_manifest(
                feature_id="payment-history-export",
                title="Add payment history export",
                priority=40,
                acceptance_criteria=[
                    "Users can export their payment history from the payment history screen",
                    "Backend returns a downloadable payment history export scoped to the authenticated user",
                    "The export includes credits purchased, payment status, and timestamps",
                    "Backend and frontend regression suites remain green",
                ],
                api_contract=[
                    "GET /api/payments/history/export",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
            )
        )

    if {
        "app/lead_gen/saved_searches/routes.py",
        "app/lead_gen/leads/routes.py",
    }.issubset(backend_files) and {
        "src/features/lead-gen/components/SavedSearchesPanel.tsx",
        "src/features/lead-gen/components/LeadsTable.tsx",
    }.issubset(frontend_files):
        suggestions.append(
            _feature_manifest(
                feature_id="saved-search-alerts",
                title="Add saved search alerts",
                priority=50,
                acceptance_criteria=[
                    "Users can enable alerts for a saved search",
                    "Backend stores alert preferences per saved search",
                    "Frontend shows alert status and lets users toggle alerts from the saved searches panel",
                    "Backend and frontend regression suites remain green",
                ],
                api_contract=[
                    "POST /api/lead_gen/saved-searches/:id/alerts",
                    "PATCH /api/lead_gen/saved-searches/:id/alerts",
                ],
                backend_repo=backend_repo,
                frontend_repo=frontend_repo,
            )
        )

    return suggestions


def _feature_manifest(
    feature_id: str,
    title: str,
    priority: int,
    acceptance_criteria: list[str],
    api_contract: list[str],
    backend_repo: Path,
    frontend_repo: Path,
) -> dict[str, Any]:
    return {
        "id": feature_id,
        "title": title,
        "status": "suggested",
        "priority": priority,
        "backend_repo": str(backend_repo),
        "frontend_repo": str(frontend_repo),
        "branches": {
            "backend": f"agent/{feature_id}-backend",
            "frontend": f"agent/{feature_id}-frontend",
        },
        "acceptance_criteria": acceptance_criteria,
        "api_contract": api_contract,
    }


def main() -> int:
    args = parse_args()
    suggestions = discover_features(
        backend_repo=args.backend_repo,
        frontend_repo=args.frontend_repo,
        features_dir=args.features_dir,
        write=args.write,
    )
    print(json.dumps({"discovered_features": suggestions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
