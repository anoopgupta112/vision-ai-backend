# Automation How It Works

This document explains what happens when you run:

```bash
./run_full_automation.sh
```

## What The Script Does

`run_full_automation.sh` is the shell entrypoint for the Codex automation flow.

It:

- resolves the backend repo path
- resolves the frontend repo path
- checks that both repos are git checkouts
- checks that `.venv/bin/python` exists
- checks that `codex` is installed
- checks that `gh` is installed
- exports the repo paths for the orchestrator
- runs `python -m automation.orchestrator` with execution flags enabled

The script currently runs:

```bash
.venv/bin/python -m automation.orchestrator \
  --discover \
  --auto-approve \
  --force-prs \
  --max-retries "$MAX_RETRIES" \
  --execute-branches \
  --execute-codex \
  --execute-validation \
  --execute-pushes \
  --execute-prs
```

## What Gets Selected

The orchestrator reads feature manifests from:

`automation/features/*.json`

Each manifest defines:

- feature id
- title
- status
- backend repo
- frontend repo
- backend branch
- frontend branch
- acceptance criteria
- API contract

Selection order:

1. Load all manifests.
2. Pick the next `approved` feature.
3. If no feature is approved and `--auto-approve` is enabled, pick the next `suggested` feature and mark it `approved`.

Because `run_full_automation.sh` includes `--auto-approve`, a suggested feature can become the next active implementation target automatically.

## Stages

The orchestrator runs these stages in order.

### 1. Discovery

The system scans backend and frontend repos and may write new suggested feature manifests.

Relevant code:

- [automation/discovery.py](/Users/anoopchandra/repositories/main_dashboard/automation/discovery.py)

### 2. Feature Selection

The next feature is chosen from the manifest list.

Relevant code:

- [automation/feature_store.py](/Users/anoopchandra/repositories/main_dashboard/automation/feature_store.py)
- [automation/orchestrator.py](/Users/anoopchandra/repositories/main_dashboard/automation/orchestrator.py)

### 3. Preflight

The system verifies prerequisites before execution starts.

Current checks include:

- backend repo exists
- frontend repo exists
- `git` exists
- `codex` exists when Codex execution is requested
- `gh` auth is valid when PR creation is requested
- webhook config exists when a webhook is requested

Relevant code:

- [automation/preflight.py](/Users/anoopchandra/repositories/main_dashboard/automation/preflight.py)

### 4. Spec Validation

The selected manifest is validated before any branch or code execution happens.

Relevant code:

- [automation/validator.py](/Users/anoopchandra/repositories/main_dashboard/automation/validator.py)

### 5. Branch Preparation

The orchestrator prepares feature branches in both repos.

Typical branch format:

- backend: `agent/<feature>-backend`
- frontend: `agent/<feature>-frontend`

Relevant code:

- [automation/branch_manager.py](/Users/anoopchandra/repositories/main_dashboard/automation/branch_manager.py)

### 6. Backend Codex Run

The orchestrator generates a backend-specific prompt and runs:

```bash
codex exec --full-auto -C <backend_repo> "<prompt>"
```

The backend prompt tells Codex to:

- update tests first
- implement only the backend side
- preserve regression behavior
- run checks
- commit changes

Relevant code:

- [automation/codex_runner.py](/Users/anoopchandra/repositories/main_dashboard/automation/codex_runner.py)
- [automation/prompt_builder.py](/Users/anoopchandra/repositories/main_dashboard/automation/prompt_builder.py)

### 7. Frontend Codex Run

The orchestrator generates a frontend-specific prompt and runs the same flow against the frontend repo.

It instructs Codex to:

- update frontend tests first
- implement only frontend work
- run frontend checks
- commit changes

Relevant code:

- [automation/codex_runner.py](/Users/anoopchandra/repositories/main_dashboard/automation/codex_runner.py)
- [automation/prompt_builder.py](/Users/anoopchandra/repositories/main_dashboard/automation/prompt_builder.py)

### 8. Validation

After backend and frontend implementation, the orchestrator runs regression checks.

This stage is the gate before push and PR creation.

Relevant code:

- [automation/validation_runner.py](/Users/anoopchandra/repositories/main_dashboard/automation/validation_runner.py)

### 9. Branch Push

If validation passes, the orchestrator commits pending changes if needed and pushes both feature branches.

Relevant code:

- [automation/push_manager.py](/Users/anoopchandra/repositories/main_dashboard/automation/push_manager.py)
- [automation/git_utils.py](/Users/anoopchandra/repositories/main_dashboard/automation/git_utils.py)

### 10. Pull Request Creation

If the run reaches the PR stage, the orchestrator opens backend and frontend PRs with `gh pr create` and then cross-links them with comments.

Relevant code:

- [automation/pr_manager.py](/Users/anoopchandra/repositories/main_dashboard/automation/pr_manager.py)
- [automation/templates.py](/Users/anoopchandra/repositories/main_dashboard/automation/templates.py)

## State Tracking

Run history is stored in:

- [automation/state.json](/Users/anoopchandra/repositories/main_dashboard/automation/state.json)

This file records:

- selected feature ids
- stage names
- stage status
- stage detail
- update timestamps

The manifest status is also updated as the run progresses.

Common statuses:

- `suggested`
- `approved`
- `in_progress`
- `pr_opened`
- `rejected`

## Retries

The orchestrator supports retry attempts for Codex and validation loops.

`MAX_RETRIES` defaults to `3` in the shell script and is passed into the Python orchestrator.

If a Codex or validation attempt fails, the failure detail is fed back into the next retry context.

## Important Behavior

- The shell script is not a dry run.
- It can implement a brand new feature.
- It can auto-approve a suggested feature.
- It can push branches.
- It can open PRs.
- It uses your local `gh` authentication when run outside the sandbox.

## How To Inspect The Result

After a run, check:

- [automation/state.json](/Users/anoopchandra/repositories/main_dashboard/automation/state.json)
- the selected feature manifest in `automation/features/`
- backend branch status with `git branch --show-current`
- frontend branch status in the frontend repo
- created PR URLs from the final JSON output

## Current Example Outcome

A successful run typically ends with JSON like:

- selected feature id
- `preflight: done`
- `backend_codex_attempt_1: done`
- `frontend_codex_attempt_1: done`
- `validation_attempt_1: done`
- `branch_push: done`
- `pull_requests: done`

That means the automation completed feature implementation, validation, push, and PR creation end to end.
