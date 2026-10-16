#!/usr/bin/env bash
# App runtime and development checks have separate generated environments.
export PATH="$PWD/.private/runtime/launcher/bin:$PWD/.codex/bin:$HOME/.local/bin:$PATH"
if [[ "${1:-dev}" == app ]]; then
    task_runtime="$PWD/.private/runtime"
else
    task_runtime="$PWD/.codex"
fi
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
    echo 'Or place the Linux uv executable in this project at .codex/bin/uv.' >&2
    exit 1
fi
