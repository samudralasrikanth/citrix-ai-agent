@echo off
:: ════════════════════════════════════════════════════════════════
::  Citrix AI Vision Agent — Windows launcher
::
::  Usage:
::    run setup              Select window/area to capture
::    run new  <name>        Create a new test playbook
::    run run  <name>        Execute a playbook
::    run run  <name> --dry-run   Preview steps only
::    run list               List all playbooks
:: ════════════════════════════════════════════════════════════════

setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV=%SCRIPT_DIR%venv"
set "VENV_PYTHON=%VENV%\Scripts\python.exe"

:: ── Check venv ────────────────────────────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo.
    echo   !!  Virtual environment not found.
    echo.
    echo   Create it:
    echo       python -m venv venv
    echo       venv\Scripts\activate
    echo       pip install -r requirements.txt
    echo.
    exit /b 1
)

:: ── Run launcher ─────────────────────────────────────────────────
"%VENV_PYTHON%" "%SCRIPT_DIR%run.py" %*
exit /b %ERRORLEVEL%
