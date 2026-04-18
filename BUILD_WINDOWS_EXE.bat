@echo off
REM Build a Windows folder app (DiscogsVinylSorter.exe + DLLs) using PyInstaller.
REM Requires: SETUP.bat completed, then optional: pip install pyinstaller

cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo ERROR: Run SETUP.bat first to create .venv
  pause
  exit /b 1
)

echo Installing PyInstaller if needed...
"%PY%" -m pip install pyinstaller --quiet

echo.
echo Building... (one-time; may take a few minutes)
"%PY%" -m PyInstaller --noconfirm --windowed --onedir --name "DiscogsVinylSorter" --collect-all customtkinter autosort_gui.py

if %ERRORLEVEL% neq 0 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo Build output:  dist\DiscogsVinylSorter\DiscogsVinylSorter.exe
echo ============================================================
echo Copy your .env next to that .exe if you use one.
echo You can pin that .exe to the taskbar or Start menu.
echo.
pause
