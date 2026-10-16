#!/usr/bin/env bash
# Sourced by run.sh and check.sh; generated tools/caches stay in this checkout.
export PATH="$PWD/.codex/launcher/bin:$PWD/.codex/bin:$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="$PWD/.codex/venv"
export UV_CACHE_DIR="$PWD/.codex/uv-cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.codex/python"
export PYTHONPYCACHEPREFIX="$PWD/.codex/pycache"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$PWD/.codex/tmp"
mkdir -p "$TMPDIR"
if ! command -v uv >/dev/null; then
    echo 'Missing Linux uv. Install it in WSL: https://docs.astral.sh/uv/getting-started/installation/' >&2
    echo 'Or place the Linux uv executable in this project at .codex/bin/uv.' >&2
    exit 1
fi
