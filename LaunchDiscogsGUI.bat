@echo off
REM Windows launcher for Discogs GUI

cd /d "%~dp0"

set PYTHON_BIN=

REM Try .venv first
if exist ".venv\Scripts\python.exe" (
    set PYTHON_BIN=.venv\Scripts\python.exe
    goto :run
)

REM Try python3 command
where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_BIN=python3
    goto :run
)

REM Try python command
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_BIN=python
    goto :run
)

REM No Python found
echo ERROR: Could not find Python. Install Python 3.9+ and/or create .venv.
echo.
pause
exit /b 1

:run
"%PYTHON_BIN%" gui_app.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Discogs GUI failed to start.
    echo If you see a Tk error, reinstall Python with Tk support from python.org
    echo and recreate your .venv.
    echo.
    pause
    exit /b 1
)
