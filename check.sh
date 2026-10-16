#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source scripts/runtime.sh
uv sync --locked --quiet
uv run --no-sync python checks/check_framework.py
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$PWD/checks/check_launcher.ps1")"
uv run --no-sync python checks/check_auth.py
uv run --no-sync python checks/check_auth_recovery.py
node.exe checks/check_device_guide.mjs
uv run --no-sync python checks/check_ai.py
uv run --no-sync python checks/check_harness.py
uv run --no-sync python checks/check_campus.py
uv run --no-sync python checks/check_analysis.py
shopt -s nullglob
for check in modules/*/checks/check_*.py; do
    uv run --no-sync python "$check"
done
