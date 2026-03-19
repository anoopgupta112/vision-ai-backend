# Automation Skeleton

This folder contains the first orchestration layer for scheduled Codex-driven feature delivery.

## Current Scope

This first version does these things:

- stores feature manifests in `automation/features/`
- validates feature manifests
- discovers suggested feature manifests by scanning backend/frontend repos
- picks the next approved feature
- tracks orchestration state in `automation/state.json`
- runs a dry-run orchestration flow
- can execute the validation stage from Python
- generates real branch, Codex, and PR command plans
- can execute backend/frontend Codex runs
- can execute PR creation with cross-link comments
- enforces stage gating so PR creation does not run after branch, Codex, or validation failures

This version does not yet:

- manage retries/recovery automatically
- prove a live Codex-authenticated GitHub Actions run end-to-end

GitHub Actions scheduling has now been scaffolded in `.github/workflows/automation-orchestrator.yml`.
The scheduled run now triggers every 30 minutes and is safe by default:

- scheduled executions run discovery and keep `--dry-run` enabled by default
- set repository variable `AUTOMATION_ENABLE_EXECUTION=true` to let scheduled runs execute branches, Codex, validation, and PR creation
- manual dispatch can opt into branch prep, Codex execution, validation, and PR creation
- repo paths are resolved from environment variables in CI
- PR creation supports richer bodies and cross-link comments when `--execute-prs` is used

## Feature Manifest Format

Store one JSON file per feature in `automation/features/`.

Example:

```json
{
  "id": "saved-searches",
  "title": "Add saved searches",
  "status": "approved",
  "priority": 10,
  "backend_repo": "${BACKEND_REPO_PATH:-/Users/anoopchandra/repositories/main_dashboard}",
  "frontend_repo": "${FRONTEND_REPO_PATH:-/Users/anoopchandra/repositories/main_dashboard_frontend}",
  "branches": {
    "backend": "agent/saved-searches-backend",
    "frontend": "agent/saved-searches-frontend"
  },
  "acceptance_criteria": [
    "User can save a search",
    "Backend stores saved search definitions",
    "Frontend lists saved searches",
    "Regression tests remain green"
  ],
  "api_contract": [
    "POST /api/lead_gen/saved-searches",
    "GET /api/lead_gen/saved-searches"
  ]
}
```

## Manual Usage

Dry run:

```bash
.venv/bin/python -m automation.orchestrator --dry-run
```

Run discovery and dry-run orchestration:

```bash
.venv/bin/python -m automation.orchestrator --discover --dry-run
```

Execute the validation stage:

```bash
.venv/bin/python -m automation.orchestrator --execute-validation
```

Execute branches + validation:

```bash
.venv/bin/python -m automation.orchestrator --execute-branches --execute-validation
```

Execute the full flow manually:

```bash
.venv/bin/python -m automation.orchestrator --discover --execute-branches --execute-codex --execute-validation --execute-prs
```

Mark the picked feature as in progress in state:

```bash
.venv/bin/python -m automation.orchestrator
```

Run discovery only and write suggested manifests:

```bash
.venv/bin/python -m automation.discovery --write
```

Inspect current state:

```bash
cat automation/state.json
```
