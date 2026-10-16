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
exec uv run --no-sync python -m backend.main "$@"
