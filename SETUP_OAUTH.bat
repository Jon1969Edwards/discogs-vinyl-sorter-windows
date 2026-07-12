@echo off
REM One-time OAuth setup — enables "Sign in with Discogs" for all users of this build.

cd /d "%~dp0"

set PYTHON_BIN=
if exist ".venv\Scripts\python.exe" (
    set PYTHON_BIN=.venv\Scripts\python.exe
    goto :run
)
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_BIN=python
    goto :run
)
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_BIN=py -3
    goto :run
)

echo ERROR: Python not found. Run SETUP.bat first.
pause
exit /b 1

:run
"%PYTHON_BIN%" setup_oauth.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo OAuth setup failed.
    pause
    exit /b 1
)
pause
