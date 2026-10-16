#!/usr/bin/env bash
export PATH="$PWD/.codex/bin:$PWD/.private/runtime/launcher/bin:$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="$PWD/.codex/venv"
export UV_CACHE_DIR="$PWD/.codex/cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/.codex/python"
export PYTHONPYCACHEPREFIX="$PWD/.codex/cache/python"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$PWD/.codex/tmp"
export XDG_CACHE_HOME="$PWD/.codex/cache"
mkdir -p "$TMPDIR"
