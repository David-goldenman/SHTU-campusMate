@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "CAMPUS_EXIT=%ERRORLEVEL%"
if not "%CAMPUS_EXIT%"=="0" (
    echo.
    echo [Campus] Startup failed. The error above is kept for inspection.
    pause
)
exit /b %CAMPUS_EXIT%
