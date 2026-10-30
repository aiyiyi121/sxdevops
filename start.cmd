@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "startupExitCode=%errorlevel%"
if not "%startupExitCode%"=="0" pause
exit /b %startupExitCode%
