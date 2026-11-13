#!/usr/bin/env bash
# Stage the pure-Python half of the backend environment for the iOS bundle.
#
# The lockfile environment is created once with uv, then every package that
# ships a macOS binary is removed: those are replaced by the iOS wheels from
# .codex/wheelhouse (or, for pypdfium2, by the PDFKit shim in Sources/py_extra).
#
# Usage: ./stage_ios_site.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
export UV_CACHE_DIR="$REPO/.codex/cache/uv"
export UV_PYTHON_INSTALL_DIR="$REPO/.codex/python"
export UV_PROJECT_ENVIRONMENT="$REPO/.codex/runtime-venv"

"$REPO/.codex/tools/bin/uv" sync --locked --python 3.13

rm -rf "$REPO/.codex/ios-site"
cp -R "$REPO/.codex/runtime-venv/lib/python3.13/site-packages" "$REPO/.codex/ios-site"

cd "$REPO/.codex/ios-site"
# Replaced by the iOS wheels.
rm -rf cryptography PIL zstandard pydantic_core pypdfium2 pypdfium2_raw
# 261 MB of Node runtimes for every desktop platform; the AI harness cannot run
# on iOS anyway (no subprocess), so keep only the Python module.
rm -rf deepseek_harness_runtime/runtime
# Optional native accelerators with pure-Python fallbacks.
rm -f _cffi_backend*.so charset_normalizer/*.so
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true

du -sh "$REPO/.codex/ios-site"
