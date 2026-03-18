# Automation Skeleton

This folder contains the first orchestration layer for scheduled Codex-driven feature delivery.

## Current Scope

This first version does these things:

- stores feature manifests in `automation/features/`
- validates feature manifests
- picks the next approved feature
- tracks orchestration state in `automation/state.json`
- runs a dry-run orchestration flow
- can execute the validation stage from Python
- generates real branch, Codex, and PR command plans
- provides clear placeholders for:
  - backend Codex execution
  - frontend Codex execution
  - PR creation

This version does not yet:

- schedule itself in GitHub Actions
- manage retries/recovery automatically
- run discovery-mode feature suggestion scans

GitHub Actions scheduling has now been scaffolded in `.github/workflows/automation-orchestrator.yml`.
The scheduled run is safe by default:

- scheduled executions run `--dry-run --execute-validation`
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

Dry run with validation commands shown:

```bash
.venv/bin/python -m automation.orchestrator --dry-run
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
.venv/bin/python -m automation.orchestrator --execute-branches --execute-codex --execute-validation --execute-prs
```

Mark the picked feature as in progress in state:

```bash
.venv/bin/python -m automation.orchestrator
```

Inspect current state:

```bash
cat automation/state.json
```
