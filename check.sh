#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export UV_PROJECT_ENVIRONMENT="$PWD/.codex/venv"
export UV_CACHE_DIR="$PWD/.codex/uv-cache"
export PYTHONPYCACHEPREFIX="$PWD/.codex/pycache"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$PWD/.codex/tmp"
mkdir -p "$TMPDIR"
uv sync --quiet
uv run --no-sync python checks/check_framework.py
uv run --no-sync python checks/check_auth.py
uv run --no-sync python checks/check_auth_recovery.py
node.exe checks/check_device_guide.mjs
uv run --no-sync python checks/check_ai.py
uv run --no-sync python checks/check_campus.py
uv run --no-sync python checks/check_analysis.py
shopt -s nullglob
for check in modules/*/checks/check_*.py; do
    uv run --no-sync python "$check"
done
