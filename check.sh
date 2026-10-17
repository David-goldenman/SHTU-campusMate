#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source checks/environment.sh
uv sync --locked --quiet
uv run --no-sync python checks/run_checks.py
