import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from automation.branch_manager import execute_branch_preparation, plan_branch_preparation
from automation.codex_runner import (
    execute_backend_codex_run,
    execute_frontend_codex_run,
    plan_backend_codex_run,
    plan_frontend_codex_run,
)
from automation.discovery import discover_features
from automation.feature_store import (
    FEATURES_DIR,
    load_feature_manifests,
    pick_next_approved_feature,
    pick_next_suggested_feature,
    update_feature_manifest_status,
)
from automation.models import FeatureManifest, StageResult
from automation.preflight import run_preflight
from automation.push_manager import execute_branch_push, plan_branch_push
from automation.pr_manager import execute_pull_requests, plan_pull_requests
from automation.state_store import STATE_FILE, append_stage_result, mark_feature_in_progress
from automation.validator import validate_feature_manifest
from automation.validation_runner import execute_validation_run, plan_validation_run
from automation.webhook import send_run_webhook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual Codex automation orchestrator")
    parser.add_argument("--features-dir", type=Path, default=FEATURES_DIR)
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--backend-repo", type=Path, default=Path("/Users/anoopchandra/repositories/main_dashboard"))
    parser.add_argument("--frontend-repo", type=Path, default=Path("/Users/anoopchandra/repositories/main_dashboard_frontend"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--auto-approve", action="store_true")
    parser.add_argument("--force-prs", action="store_true")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--execute-pushes", action="store_true")
    parser.add_argument("--webhook-url", type=str, default=os.environ.get("AUTOMATION_WEBHOOK_URL", "").strip())
    parser.add_argument("--execute-branches", action="store_true")
    parser.add_argument("--execute-codex", action="store_true")
    parser.add_argument("--execute-validation", action="store_true")
    parser.add_argument("--execute-prs", action="store_true")
    return parser.parse_args()


def build_plan() -> List[StageResult]:
    return [
        StageResult("discovery", "pending", "Scan backend and frontend repos and write suggested features"),
        StageResult("feature_selection", "pending", "Pick an approved feature or auto-promote a suggested feature"),
        StageResult("preflight", "pending", "Verify Codex, GitHub, repo, and webhook prerequisites"),
        StageResult("spec_validation", "pending", "Validate the approved feature manifest"),
        StageResult("branch_preparation", "pending", "Prepare backend and frontend feature branches"),
        StageResult("backend_codex", "pending", "Run backend Codex worker"),
        StageResult("frontend_codex", "pending", "Run frontend Codex worker"),
        StageResult("validation", "pending", "Run backend and frontend regression gates"),
        StageResult("branch_push", "pending", "Commit/push backend and frontend branches"),
        StageResult("pull_requests", "pending", "Open and cross-link frontend/backend PRs"),
        StageResult("webhook", "pending", "Send automation run details to the configured webhook"),
    ]


def main() -> int:
    args = parse_args()
    stage_results: List[StageResult] = []

    if args.discover:
        suggestions = discover_features(
            backend_repo=args.backend_repo,
            frontend_repo=args.frontend_repo,
            features_dir=args.features_dir,
            write=True,
        )
        stage_results.append(
            StageResult(
                name="discovery",
                status="done",
                detail=f"Discovered {len(suggestions)} new suggested feature(s).",
            )
        )

    manifests = load_feature_manifests(args.features_dir)
    try:
        feature = pick_next_approved_feature(manifests)
        stage_results.append(
            StageResult("feature_selection", "done", f"Selected approved feature: {feature.id}")
        )
    except ValueError:
        if not args.auto_approve:
            return _finish(
                args,
                None,
                stage_results or [StageResult("feature_selection", "skipped", "No approved feature manifests found.")],
            )
        try:
            feature = pick_next_suggested_feature(manifests)
        except ValueError:
            return _finish(
                args,
                None,
                stage_results or [StageResult("feature_selection", "skipped", "No approved or suggested feature manifests found.")],
            )

        stage_results.append(
            StageResult("feature_selection", "done", f"Auto-approved suggested feature: {feature.id}")
        )
        if not args.dry_run:
            update_feature_manifest_status(feature, "approved")
            manifests = load_feature_manifests(args.features_dir)
            feature = pick_next_approved_feature(manifests)

    issues = validate_feature_manifest(feature)
    if issues:
        stage_results.append(StageResult("spec_validation", "failed", "; ".join(issues)))
        if not args.dry_run:
            update_feature_manifest_status(feature, "rejected")
        return _finish(args, feature, stage_results)

    preflight_stage = run_preflight(
        feature,
        require_codex=args.execute_codex,
        require_github=args.execute_prs,
        require_webhook=bool(args.webhook_url),
    )
    stage_results.append(preflight_stage)
    if _is_failed(preflight_stage):
        return _finish(args, feature, stage_results)

    stage_results.append(StageResult("spec_validation", "done", f"Validated feature manifest: {feature.id}"))
    if not args.dry_run:
        update_feature_manifest_status(feature, "in_progress")

    branch_stage = execute_branch_preparation(feature) if args.execute_branches else plan_branch_preparation(feature)
    stage_results.append(branch_stage)
    if _is_failed(branch_stage):
        return _finish(args, feature, stage_results)

    retry_context = ""
    terminal_failure = False
    for attempt in range(1, max(args.max_retries, 1) + 1):
        if args.execute_codex:
            backend_codex_stage = execute_backend_codex_run(feature, extra_context=retry_context, attempt=attempt)
            stage_results.append(backend_codex_stage)
            if _is_exhausted(backend_codex_stage):
                terminal_failure = True
                break
            if _is_failed(backend_codex_stage):
                retry_context = backend_codex_stage.detail
                if attempt == args.max_retries:
                    terminal_failure = True
                    break
                continue

            frontend_codex_stage = execute_frontend_codex_run(feature, extra_context=retry_context, attempt=attempt)
            stage_results.append(frontend_codex_stage)
            if _is_exhausted(frontend_codex_stage):
                terminal_failure = True
                break
            if _is_failed(frontend_codex_stage):
                retry_context = frontend_codex_stage.detail
                if attempt == args.max_retries:
                    terminal_failure = True
                    break
                continue
        else:
            stage_results.append(plan_backend_codex_run(feature, extra_context=retry_context, attempt=attempt))
            stage_results.append(plan_frontend_codex_run(feature, extra_context=retry_context, attempt=attempt))

        validation_stage = execute_validation_run(feature) if args.execute_validation else plan_validation_run(feature)
        validation_stage.name = f"validation_attempt_{attempt}"
        stage_results.append(validation_stage)

        if not _is_failed(validation_stage):
            break

        retry_context = validation_stage.detail
        if attempt == args.max_retries:
            terminal_failure = True
            break

        stage_results.append(
            StageResult(
                name=f"retry_attempt_{attempt}",
                status="done",
                detail=f"Retrying Codex after validation failure: attempt {attempt + 1} of {args.max_retries}.",
            )
        )

    if terminal_failure and not (args.execute_prs and args.force_prs):
        return _finish(args, feature, stage_results)

    if terminal_failure and args.execute_prs and args.force_prs:
        stage_results.append(
            StageResult(
                "failure_override",
                "done",
                "Automation failed or Codex was exhausted, but PR creation was forced by --force-prs.",
            )
        )

    push_stage = (
        execute_branch_push(feature, report_only=terminal_failure or _has_failures(stage_results))
        if args.execute_pushes
        else plan_branch_push(feature)
    )
    stage_results.append(push_stage)
    if _is_failed(push_stage) and not (args.execute_prs and args.force_prs):
        return _finish(args, feature, stage_results)

    pr_stage = (
        execute_pull_requests(feature, stage_results, draft=_should_open_draft_pr(stage_results))
        if args.execute_prs
        else plan_pull_requests(feature, stage_results, draft=_should_open_draft_pr(stage_results))
    )
    stage_results.append(pr_stage)

    return _finish(args, feature, stage_results)


def _finish(args: argparse.Namespace, feature: Optional[FeatureManifest], stage_results: List[StageResult]) -> int:
    output = _build_output(args, feature, stage_results)

    if not args.dry_run and feature is not None and args.webhook_url:
        webhook_stage = send_run_webhook(args.webhook_url, output)
        stage_results.append(webhook_stage)
        output = _build_output(args, feature, stage_results)

    print(json.dumps(output, indent=2))

    if args.dry_run or feature is None:
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

    _sync_feature_manifest_status(feature, stage_results)

    return 0 if not _has_failures(stage_results) else 1


def _build_output(args: argparse.Namespace, feature: Optional[FeatureManifest], stage_results: List[StageResult]) -> dict:
    return {
        "selected_feature": (
            {
                "id": feature.id,
                "title": feature.title,
                "source_file": feature.source_file,
            }
            if feature
            else None
        ),
        "dry_run": args.dry_run,
        "max_retries": args.max_retries,
        "stage_results": [stage_result.__dict__ for stage_result in stage_results],
    }


def _is_failed(stage_result: StageResult) -> bool:
    return stage_result.status == "failed"


def _is_exhausted(stage_result: StageResult) -> bool:
    return stage_result.status == "exhausted"


def _has_failures(stage_results: List[StageResult]) -> bool:
    return any(stage.status in {"failed", "exhausted"} for stage in stage_results)


def _should_open_draft_pr(stage_results: List[StageResult]) -> bool:
    return _has_failures(stage_results)


def _sync_feature_manifest_status(feature: FeatureManifest, stage_results: List[StageResult]) -> None:
    by_name = {stage.name: stage for stage in stage_results}

    if "pull_requests" in by_name and by_name["pull_requests"].status == "done":
        update_feature_manifest_status(feature, "pr_opened")
        return

    if "spec_validation" in by_name and by_name["spec_validation"].status == "failed":
        update_feature_manifest_status(feature, "rejected")
        return

    if any(stage.status in {"failed", "exhausted"} for stage in stage_results):
        update_feature_manifest_status(feature, "approved")
        return

    if feature.status != "in_progress":
        update_feature_manifest_status(feature, "in_progress")


if __name__ == "__main__":
    raise SystemExit(main())
