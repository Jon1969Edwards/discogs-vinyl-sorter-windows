@echo off
REM Build a Windows folder app (Spindle.exe + DLLs) using PyInstaller.
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
echo Generate app icon (optional)...
"%PY%" scripts\generate_icon.py

echo.
echo Building... (one-time; may take a few minutes)
"%PY%" -m PyInstaller --noconfirm Spindle.spec

if %ERRORLEVEL% neq 0 (
  echo.
  echo Build failed.
  pause
  exit /b 1
)

echo.
if exist "certs\spindle-dev-codesign.pfx" (
  echo Signing Spindle.exe with local code-signing certificate...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sign_windows_exe.ps1"
  if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNING: Build succeeded but signing failed.
    echo          Install the Windows SDK Signing Tools, or run SIGN_WINDOWS.bat later.
    echo          See docs\CODE_SIGNING.md
    echo.
  )
) else if defined SPINDLE_CODESIGN_PFX (
  echo Signing Spindle.exe with SPINDLE_CODESIGN_PFX...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sign_windows_exe.ps1"
  if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNING: Build succeeded but signing failed. See docs\CODE_SIGNING.md
    echo.
  )
) else (
  echo NOTE: No local code-signing cert found. Unsigned builds may be blocked by
  echo       Smart App Control. Run SETUP_LOCAL_CODESIGN.bat once, then rebuild,
  echo       or run SIGN_WINDOWS.bat after installing the Windows SDK.
  echo       See docs\CODE_SIGNING.md
  echo.
)

echo.
echo ============================================================
echo Build output:  dist\Spindle\Spindle.exe
echo ============================================================
echo Copy your .env next to that .exe if you use one.
echo You can pin that .exe to the taskbar or Start menu.
echo.
pause
