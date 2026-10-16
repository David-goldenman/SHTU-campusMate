#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export UV_PROJECT_ENVIRONMENT="$PWD/.private/runtime/venv"
export UV_CACHE_DIR="$PWD/.private/runtime/cache/uv"
export PYTHONPYCACHEPREFIX="$PWD/.private/runtime/cache/python"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$PWD/.private/runtime/tmp"
export XDG_CACHE_HOME="$PWD/.private/runtime/cache"
mkdir -p "$TMPDIR"
uv sync --quiet
exec uv run --no-sync python -m backend.main "$@"
