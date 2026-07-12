@echo off
REM Windows setup script - creates venv and installs dependencies

cd /d "%~dp0"

echo.
echo ==================================================
echo Spindle - Windows Setup
echo ==================================================
echo.

REM Check for Python
set PYTHON_BIN=
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_BIN=python
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set PYTHON_BIN=python3
    ) else (
        echo ERROR: Python not found. Please install Python 3.9+ from python.org
        echo.
        pause
        exit /b 1
    )
)

echo Using Python: %PYTHON_BIN%
%PYTHON_BIN% --version
echo.

REM Create virtual environment (remove stale .venv first — fixes Errno 13 / Permission denied)
if exist ".venv" (
    echo Removing existing .venv folder ^(clean recreate^)...
    rmdir /s /q ".venv" 2>nul
    if exist ".venv" (
        echo.
        echo ERROR: Cannot delete .venv — something still has files open.
        echo   1. Close this project in Cursor/VS Code, and any terminals running Python here.
        echo   2. End Task Manager - any "python.exe" from this folder.
        echo   3. If the project is under OneDrive, pause sync or move the folder out of Desktop.
        echo   4. Manually delete the folder: %CD%\.venv
        echo   5. Run SETUP.bat again.
        echo.
        pause
        exit /b 1
    )
)

echo Creating virtual environment...
%PYTHON_BIN% -m venv .venv
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to create virtual environment.
    echo If you see permission errors: close all terminals/IDE using this folder, delete the
    echo .venv folder yourself, temporarily pause antivirus for this folder, then retry.
    echo.
    pause
    exit /b 1
)

REM Activate and install dependencies
echo.
echo Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to install dependencies
    echo.
    pause
    exit /b 1
)

echo.
echo ==================================================
echo Setup complete!
echo ==================================================
echo.
echo You can now run:
echo   - SETUP_OAUTH.bat (one-time: enable Sign in with Discogs)
echo   - LaunchAutoSortGUI.bat (Auto-Sort GUI)
echo.
echo Or use the command line:
echo   .venv\Scripts\python discogs_app.py --help
echo.
pause
