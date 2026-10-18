@echo off
setlocal
set "campus_entry=run.ps1"
if defined CAMPUS_PYTHON set "campus_entry=run-local.ps1"
if exist "%~dp0python-path.txt" set "campus_entry=run-local.ps1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0%campus_entry%" %*
set "launch_exit=%errorlevel%"
if not "%launch_exit%"=="0" pause
exit /b %launch_exit%
