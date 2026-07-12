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

REM Bundled OAuth credentials live in core\discogs_oauth_secrets.py (gitignored).
REM It is loaded dynamically at runtime, so PyInstaller can't auto-detect it:
REM include it (and the fallback module) explicitly so "Sign in with Discogs" works.
if not exist "core\discogs_oauth_secrets.py" (
  echo WARNING: core\discogs_oauth_secrets.py not found.
  echo          The build will NOT have one-click "Sign in with Discogs".
  echo          Copy core\discogs_oauth_secrets.example.py and add your keys first.
  echo.
)

echo.
echo Preparing build folder...
"%PY%" scripts\prebuild_cleanup.py
if %ERRORLEVEL% neq 0 (
  pause
  exit /b 1
)

echo.
echo Building... (one-time; may take a few minutes)
"%PY%" -m PyInstaller --noconfirm --windowed --onedir --name "DiscogsVinylSorter" --collect-all customtkinter --collect-all pygame --hidden-import core.discogs_oauth_secrets --hidden-import core.discogs_oauth_app --hidden-import core.config_store --hidden-import core.format_filter --hidden-import core.build_service --hidden-import core.audio_preview --hidden-import core.preview_player --hidden-import gui.audio_preview_panel --hidden-import gui.settings_panel --hidden-import gui.oauth_setup_dialog --hidden-import gui.tooltip --hidden-import gui.spinning_record --hidden-import gui.thumbnails --hidden-import gui.order_panel --hidden-import gui.wishlist_panel --hidden-import requests_oauthlib --hidden-import dotenv autosort_gui.py

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
