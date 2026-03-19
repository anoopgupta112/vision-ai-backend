# PR Automation Flow

This document explains how pull request opening works in the current automation setup.

## Current Status

The automation system is partially implemented.

What works now:

- feature manifests are stored in `automation/features/*.json`
- discovery can scan both repos and write new `suggested` feature manifests
- the orchestrator picks the next `approved` feature
- it builds a staged plan for:
  - branch preparation
  - backend Codex execution
  - frontend Codex execution
  - validation
  - PR creation
- execution now stops before PR creation if branch prep, Codex, or validation fails
- the PR step already knows:
  - backend repo
  - frontend repo
  - branch names
  - PR titles
  - PR bodies
  - cross-link comment text

What is not yet complete:

- the scheduled GitHub Actions workflow has not been validated in a full live run
- discovery suggestions still use deterministic heuristics, not LLM reasoning

## How PR Opening Works Now

### 1. Feature manifest

The orchestrator reads a feature file like:

`automation/features/sample_saved_searches.json`

That file defines:

- feature id
- title
- backend repo path
- frontend repo path
- backend branch name
- frontend branch name
- acceptance criteria
- API contract

### 2. Branch preparation

The orchestrator prepares two feature branches:

- backend branch
- frontend branch

Current example:

- backend: `agent/saved-searches-backend`
- frontend: `agent/saved-searches-frontend`

### 3. Codex execution

The orchestrator builds two separate Codex prompts:

- one for backend
- one for frontend

The prompts tell Codex to:

- write/update failing tests first
- implement only that repo’s part
- preserve existing regression behavior
- run checks
- commit changes
- stop before merge

### 4. Validation

The orchestrator knows the validation gates:

- backend:
  - `.venv/bin/python -m unittest discover -s tests`
- frontend:
  - `npm run test`
  - `npm run lint`
  - `npm run build`

### 5. PR creation

When the PR stage runs, it uses `gh pr create`.

Backend PR command shape:

```bash
gh pr create \
  --repo anoopgupta112/platform-infra \
  --head agent/saved-searches-backend \
  --title "feat: Add saved searches (backend)" \
  --body "<generated backend PR body>"
```

Frontend PR command shape:

```bash
gh pr create \
  --repo anoopgupta112/vision-ai-frontend \
  --head agent/saved-searches-frontend \
  --title "feat: Add saved searches (frontend)" \
  --body "<generated frontend PR body>"
```

### 6. Cross-link comments

After both PRs are created, the orchestrator is set up to comment on both PRs:

- backend PR gets a comment with the frontend PR URL
- frontend PR gets a comment with the backend PR URL

It uses:

```bash
gh pr comment
```

## Where This Logic Lives

- orchestrator entry point:
  - `automation/orchestrator.py`
- PR planning/execution:
  - `automation/pr_manager.py`
- PR body/comment templates:
  - `automation/templates.py`
- prompt generation:
  - `automation/prompt_builder.py`
- validation:
  - `automation/validation_runner.py`
- branch handling:
  - `automation/branch_manager.py`

## Manual Runs

Dry run only:

```bash
.venv/bin/python -m automation.orchestrator --dry-run
```

Execute validation only:

```bash
.venv/bin/python -m automation.orchestrator --execute-validation
```

Execute full manual flow:

```bash
.venv/bin/python -m automation.orchestrator \
  --discover \
  --execute-branches \
  --execute-codex \
  --execute-validation \
  --execute-prs
```

## Important Safety Rule

The orchestrator now enforces:

`do not open PRs unless branch prep, Codex, and validation all pass`
