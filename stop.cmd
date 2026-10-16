@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-local.ps1" --stop
set "CAMPUS_EXIT=%ERRORLEVEL%"
if not "%CAMPUS_EXIT%"=="0" (
    echo.
    echo [Campus] Stop failed. The error above is kept for inspection.
    pause
)
exit /b %CAMPUS_EXIT%
