@echo off
REM ASCII-only launcher: the menu UI lives in tools\menu.py
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"
"%PY%" "tools\menu.py"
if errorlevel 1 pause
exit /b
