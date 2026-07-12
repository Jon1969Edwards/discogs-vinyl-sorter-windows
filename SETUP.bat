@echo off
REM Windows setup script - creates venv and installs dependencies

cd /d "%~dp0"

echo.
echo ==================================================
echo Spindle - Windows Setup
echo ==================================================
echo.

REM Prefer Python 3.12 for pygame wheels; fall back to python / python3
set PYTHON_BIN=
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3.12 -c "pass" >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_BIN=py -3.12"
    )
)
if not defined PYTHON_BIN (
    where python >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set PYTHON_BIN=python
    ) else (
        where python3 >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            set PYTHON_BIN=python3
        ) else (
            echo ERROR: Python not found. Install Python 3.12 from python.org
            echo        ^(recommended^) — Python 3.13+ may not support audio preview yet.
            echo.
            pause
            exit /b 1
        )
    )
)

echo Using Python: %PYTHON_BIN%
%PYTHON_BIN% --version
echo.

for /f "delims=" %%v in ('%PYTHON_BIN% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_MM=%%v
if "%PY_MM%"=="3.13" (
    echo WARNING: Python 3.13+ detected. Core app will install, but Pro audio preview
    echo          ^(pygame^) may be unavailable until prebuilt wheels exist.
    echo          For full support, install Python 3.12 from python.org and re-run SETUP.bat
    echo.
)
if "%PY_MM%"=="3.14" (
    echo WARNING: Python 3.14 detected. Core app will install, but Pro audio preview
    echo          ^(pygame^) is not available on 3.14 yet. Install Python 3.12 from
    echo          python.org for audio preview, or continue without it.
    echo.
)

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
echo Installing core dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to install core dependencies
    echo.
    pause
    exit /b 1
)

echo.
echo Installing optional audio preview dependencies ^(pygame^)...
pip install -r requirements-audio.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNING: pygame could not be installed. The app will run; Pro audio preview
    echo          will be unavailable. Use Python 3.12 and run SETUP.bat again to fix.
    echo.
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
