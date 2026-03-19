#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_REPO_PATH="${BACKEND_REPO_PATH:-$ROOT_DIR}"
FRONTEND_REPO_PATH="${FRONTEND_REPO_PATH:-/Users/anoopchandra/repositories/main_dashboard_frontend}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
MAX_RETRIES="${MAX_RETRIES:-3}"
AUTOMATION_WEBHOOK_URL="${AUTOMATION_WEBHOOK_URL:-}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ ! -d "$BACKEND_REPO_PATH/.git" ]]; then
  echo "Backend repo is not a git checkout: $BACKEND_REPO_PATH" >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_REPO_PATH/.git" ]]; then
  echo "Frontend repo is not a git checkout: $FRONTEND_REPO_PATH" >&2
  exit 1
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "codex command not found" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh command not found" >&2
  exit 1
fi

export BACKEND_REPO_PATH
export FRONTEND_REPO_PATH
export AUTOMATION_WEBHOOK_URL

exec "$PYTHON_BIN" -m automation.orchestrator \
  --discover \
  --auto-approve \
  --force-prs \
  --max-retries "$MAX_RETRIES" \
  --execute-branches \
  --execute-codex \
  --execute-validation \
  --execute-pushes \
  --execute-prs \
  "$@"
