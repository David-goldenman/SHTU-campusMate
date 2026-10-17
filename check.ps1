$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $PSScriptRoot '.codex/windows-venv'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.codex/cache/uv-windows'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.codex/python-windows'
$env:TEMP = Join-Path $PSScriptRoot '.codex/tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
uv sync --locked
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$python = Join-Path $env:UV_PROJECT_ENVIRONMENT 'Scripts/python.exe'
& $python checks/run_checks.py
exit $LASTEXITCODE
