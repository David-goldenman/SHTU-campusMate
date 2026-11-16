$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$projectRoot = (Get-Location).Path
$env:UV_PROJECT_ENVIRONMENT = Join-Path $projectRoot '.codex/windows-venv'
$env:UV_CACHE_DIR = Join-Path $projectRoot '.codex/cache/uv-windows'
$env:electron_config_cache = Join-Path $projectRoot '.codex/cache/electron'
$env:ELECTRON_BUILDER_CACHE = Join-Path $projectRoot '.codex/cache/electron-builder'
$env:ELECTRON_GET_USE_PROXY = 'true'
$env:TEMP = Join-Path $projectRoot '.codex/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP, '.codex/desktop-build' -Force | Out-Null
uv sync --locked
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Copy-Item -LiteralPath desktop/package.json, desktop/package-lock.json -Destination .codex/desktop-build -Force
npm.cmd ci --prefix .codex/desktop-build --cache .codex/cache/npm --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node .codex/desktop-build/node_modules/electron/install.js
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.codex/windows-venv/Scripts/python.exe' -X utf8 -B packaging/build_windows.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node packaging/build_desktop.cjs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
node packaging/build_installer.cjs
exit $LASTEXITCODE
