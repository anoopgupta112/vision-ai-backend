import argparse
import json
from pathlib import Path
from typing import List

from automation.branch_manager import execute_branch_preparation, plan_branch_preparation
from automation.codex_runner import (
    execute_backend_codex_run,
    execute_frontend_codex_run,
    plan_backend_codex_run,
    plan_frontend_codex_run,
)
from automation.feature_store import FEATURES_DIR, load_feature_manifests, pick_next_approved_feature
from automation.models import StageResult
from automation.pr_manager import execute_pull_requests, plan_pull_requests
from automation.state_store import STATE_FILE, append_stage_result, mark_feature_in_progress
from automation.validator import validate_feature_manifest
from automation.validation_runner import execute_validation_run, plan_validation_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual Codex automation orchestrator skeleton")
    parser.add_argument("--features-dir", type=Path, default=FEATURES_DIR)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute-branches", action="store_true")
    parser.add_argument("--execute-codex", action="store_true")
    parser.add_argument("--execute-validation", action="store_true")
    parser.add_argument("--execute-prs", action="store_true")
    return parser.parse_args()


def build_plan() -> List[StageResult]:
    return [
        StageResult("spec_validation", "pending", "Validate the approved feature manifest"),
        StageResult("branch_preparation", "pending", "Prepare backend and frontend feature branches"),
        StageResult("backend_codex", "pending", "Run backend Codex worker"),
        StageResult("frontend_codex", "pending", "Run frontend Codex worker"),
        StageResult("validation", "pending", "Run backend and frontend regression gates"),
        StageResult("pull_requests", "pending", "Open and cross-link frontend/backend PRs"),
    ]


def main() -> int:
    args = parse_args()
    manifests = load_feature_manifests(args.features_dir)
    feature = pick_next_approved_feature(manifests)
    issues = validate_feature_manifest(feature)

    stage_results: List[StageResult] = []
    if issues:
        stage_results.append(
            StageResult(
                name="spec_validation",
                status="failed",
                detail="; ".join(issues),
            )
        )
    else:
        stage_results.append(
            StageResult(
                name="spec_validation",
                status="done",
                detail=f"Validated feature manifest: {feature.id}",
            )
        )
        if args.execute_branches:
            stage_results.append(execute_branch_preparation(feature))
        else:
            stage_results.append(plan_branch_preparation(feature))

        if args.execute_codex:
            stage_results.append(execute_backend_codex_run(feature))
            stage_results.append(execute_frontend_codex_run(feature))
        else:
            stage_results.append(plan_backend_codex_run(feature))
            stage_results.append(plan_frontend_codex_run(feature))

        if args.execute_validation:
            stage_results.append(execute_validation_run(feature))
        else:
            stage_results.append(plan_validation_run(feature))

        if args.execute_prs:
            stage_results.append(execute_pull_requests(feature))
        else:
            stage_results.append(plan_pull_requests(feature))

    output = {
        "selected_feature": {
            "id": feature.id,
            "title": feature.title,
            "source_file": feature.source_file,
        },
        "dry_run": args.dry_run,
        "stage_results": [stage_result.__dict__ for stage_result in stage_results],
    }

    print(json.dumps(output, indent=2))

    if args.dry_run:
        return 0

    mark_feature_in_progress(feature.id, args.state_file)
    for stage_result in stage_results:
        append_stage_result(
            feature.id,
            stage_result.name,
            stage_result.status,
            stage_result.detail,
            args.state_file,
        )

    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
