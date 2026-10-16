#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source scripts/runtime.sh app
if [[ "${1:-}" == --check ]]; then
    uv --version
    for tool in powershell.exe node.exe; do
        command -v "$tool" >/dev/null || { echo "Missing Windows tool: $tool" >&2; exit 1; }
    done
    echo 'Launch dependencies found. Python 3.12+ and locked packages are prepared on launch.'
    if ! command -v node >/dev/null || ! command -v pnpm >/dev/null; then
        echo 'AI plugins additionally need Linux Node.js 22+ and pnpm in PATH.'
    fi
    exit 0
fi
uv sync --locked --quiet
exec uv run --no-sync python -m backend.main "$@"
