@echo off
REM ASCII-only launcher: the real installer UI lives in install.ps1
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 pause
exit /b
