# Codex Automation Progress

This file tracks the setup work for scheduled Codex-driven backend and frontend feature development.

## Repositories

- Backend: `/Users/anoopchandra/repositories/main_dashboard`
- Frontend: `/Users/anoopchandra/repositories/main_dashboard_frontend`

## Overall Status

- Progress: baseline safety net is in place
- Current phase: orchestration skeleton
- Next major phase: Codex execution and scheduled workflow

## Steps

### 1. Identify actual backend/frontend repos
- Status: Done
- Notes:
  - Backend confirmed as `main_dashboard`
  - Frontend confirmed as `main_dashboard_frontend`

### 2. Define the safe delivery model
- Status: Done
- Notes:
  - Agreed flow is:
    - keep baseline tests for current features
    - add new feature tests
    - let Codex implement
    - run old + new tests
    - open PR only if all checks pass

### 3. Add backend baseline regression tests
- Status: Done
- Coverage added:
  - app smoke tests
  - auth and permission tests
  - lead generation route tests
  - admin route tests
- Current backend test count:
  - 27 passing tests

### 4. Add frontend baseline regression tests
- Status: Done
- Coverage added:
  - auth store behavior
  - protected route behavior
  - landing/dashboard rendering
  - sidebar/layout behavior
  - lead generation workflow
  - admin dashboard workflow
- Current frontend test count:
  - 19 passing tests

### 5. Set up frontend test tooling
- Status: Done
- Notes:
  - Vitest added
  - Testing Library added
  - shared test setup added
  - ESLint config added so lint can run consistently

### 6. Validate current test and build gates
- Status: Done
- Backend checks:
  - `python -m unittest ...` passes
- Frontend checks:
  - `npm run test` passes
  - `npm run lint` passes
  - `npm run build` passes

### 7. Create shared progress tracking
- Status: Done
- Notes:
  - This file is the first tracking document

### 8. Define feature intake format
- Status: Done
- Needed:
  - chosen local manifest format: `automation/features/*.json`
  - defined statuses:
    - suggested
    - approved
    - in_progress
    - pr_opened
    - merged
    - rejected

### 9. Build the automation/orchestrator layer
- Status: In Progress
- Needed files/modules:
  - scheduler
  - feature picker
  - spec builder
  - Codex runner
  - validator
  - PR creator
- Done in first pass:
  - feature manifest loader
  - manifest validator
  - state store
  - dry-run orchestrator
  - validation runner
  - branch preparation planner
  - backend/frontend Codex command planner
  - PR command planner
  - Python execution adapters for branches
  - Python execution adapters for Codex
  - Python execution adapters for PR creation
  - strict stage gating before PR execution
  - graceful no-approved-feature handling
- Still pending in this step:
  - recovery/retry handling
  - richer execution logging

### 10. Add scheduled execution
- Status: In Progress
- Options:
  - GitHub Actions scheduled workflow
  - local cron-based runner
- Done in first pass:
  - GitHub Actions workflow scaffolded
  - scheduled mode runs every 30 minutes
  - scheduled mode runs safely in dry-run
  - scheduled mode can be promoted to full execution with repository variable `AUTOMATION_ENABLE_EXECUTION=true`
  - workflow_dispatch supports controlled execution flags
- Still pending in this step:
  - verify workflow against real Codex-authenticated execution
  - add retry/reporting behavior

### 11. Add Codex backend worker flow
- Status: Pending
- Target behavior:
  - read approved feature
  - write or verify failing feature tests
  - implement backend
  - run backend regression suite
  - prepare backend PR

### 12. Add Codex frontend worker flow
- Status: Pending
- Target behavior:
  - read approved feature and API contract
  - write or verify failing feature tests
  - implement frontend
  - run frontend regression/build/lint
  - prepare frontend PR

### 13. Add PR cross-linking and validation rules
- Status: In Progress
- Rules to enforce:
  - no PR if checks fail
  - no auto-merge
  - link backend PR and frontend PR
  - require human review
- Done in first pass:
  - richer backend/frontend PR body templates
  - cross-link comment templates
  - PR execution path now comments on both PRs after creation
  - orchestrator now enforces validation-before-PR in execution flow
- Still pending in this step:
  - add draft PR support and richer metadata

### 14. Add discovery mode for feature suggestions
- Status: In Progress
- Target behavior:
  - scan backend code
  - suggest feature ideas
  - wait for human approval before coding
- Done in first pass:
  - deterministic repo scan across backend and frontend
  - suggested manifests written into `automation/features`
- Still pending in this step:
  - richer heuristics and ranking
  - optional LLM-based suggestion generation

## Current Done Summary

- Repo mapping completed
- Delivery structure defined
- Backend regression baseline completed
- Frontend regression baseline completed
- Validation gates are green
- Feature intake format created
- Orchestrator skeleton started

## Current Pending Summary

- live Codex-authenticated workflow verification
- hardened schedule runner with retries/reporting
- richer discovery workflow

## Recommended Next Step

Verify and harden the live workflow:

1. run a Codex-authenticated scheduled/manual workflow in GitHub Actions
2. confirm branch push and PR creation in both repos
3. improve discovery heuristics and ranking
4. then add retries/recovery
