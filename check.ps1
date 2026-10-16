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
$checks = @('checks/check_framework.py','checks/check_module_boundaries.py','checks/check_auth.py','checks/check_auth_recovery.py','checks/check_auth_browser.py','checks/check_ai.py','checks/check_harness.py','checks/check_campus.py')
$checks += Get-ChildItem modules/*/checks/check_*.py | ForEach-Object { $_.FullName }
foreach ($check in $checks) {
    & $python $check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
foreach ($check in @('checks/check_frontend.mjs','checks/check_device_guide.mjs')) {
    node.exe $check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File checks/check_launcher.ps1
exit $LASTEXITCODE
