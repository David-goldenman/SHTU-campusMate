#!/usr/bin/env bash
# Application runtime under the workspace's private directory.
export PATH="$PWD/.private/runtime/launcher/bin:$HOME/.local/bin:$PATH"
task_runtime="$PWD/.private/runtime"
export UV_PROJECT_ENVIRONMENT="$task_runtime/venv"
export UV_CACHE_DIR="$task_runtime/cache/uv"
export UV_PYTHON_INSTALL_DIR="$task_runtime/python"
export PYTHONPYCACHEPREFIX="$task_runtime/cache/python"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$task_runtime/tmp"
export XDG_CACHE_HOME="$task_runtime/cache"
mkdir -p "$TMPDIR"
unset task_runtime
if ! command -v uv >/dev/null; then
    echo 'Missing Linux uv. Install it in WSL: https://docs.astral.sh/uv/getting-started/installation/' >&2
    exit 1
fi
