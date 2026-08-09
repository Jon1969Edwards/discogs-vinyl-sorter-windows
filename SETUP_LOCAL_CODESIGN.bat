@echo off
REM Create a local Spindle code-signing certificate (CurrentUser trust).
REM See docs\CODE_SIGNING.md

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_local_codesign_cert.ps1"
if %ERRORLEVEL% neq 0 (
  echo.
  echo Certificate setup failed.
  pause
  exit /b 1
)
echo.
pause
