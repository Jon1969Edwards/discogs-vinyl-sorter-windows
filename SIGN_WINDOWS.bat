@echo off
REM Sign dist\Spindle\Spindle.exe (and installer if present).
REM Run SETUP_LOCAL_CODESIGN.bat once first, or set SPINDLE_CODESIGN_PFX.

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sign_windows_exe.ps1" %*
if %ERRORLEVEL% neq 0 (
  echo.
  echo Signing failed.
  pause
  exit /b 1
)
echo.
pause
