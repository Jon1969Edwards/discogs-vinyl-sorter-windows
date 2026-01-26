@echo off
REM Windows setup script - creates venv and installs dependencies

cd /d "%~dp0"

echo.
echo ==================================================
echo Discogs Vinyl Sorter - Windows Setup
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

REM Create virtual environment
echo Creating virtual environment...
%PYTHON_BIN% -m venv .venv
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to create virtual environment
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
echo   - LaunchDiscogsGUI.bat (main GUI)
echo   - LaunchAutoSortGUI.bat (auto-sort GUI)
echo.
echo Or use the command line:
echo   .venv\Scripts\python discogs_app.py --help
echo.
pause
