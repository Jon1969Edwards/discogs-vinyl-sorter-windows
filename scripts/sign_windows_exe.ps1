#Requires -Version 5.1
<#
.SYNOPSIS
  Sign Spindle Windows executables with Authenticode (signtool).

.DESCRIPTION
  Uses certs\spindle-dev-codesign.pfx by default (created by create_local_codesign_cert.ps1),
  or SPINDLE_CODESIGN_PFX / SPINDLE_CODESIGN_PASSWORD (or WINDOWS_CERT_* aliases).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\sign_windows_exe.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\sign_windows_exe.ps1 -Path dist\Spindle\Spindle.exe,dist\installer\Spindle-Setup-1.0.0.exe
#>
[CmdletBinding()]
param(
  [string[]]$Path = @(),
  [string]$PfxPath = "",
  [string]$PfxPassword = "",
  [string]$TimestampUrl = "http://timestamp.digicert.com",
  [switch]$SkipTimestamp
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Find-SignTool {
  $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $kitRoots = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
    "${env:ProgramFiles}\Windows Kits\10\bin"
  )
  foreach ($kitRoot in $kitRoots) {
    if (-not (Test-Path $kitRoot)) { continue }
    $found = Get-ChildItem -Path $kitRoot -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($found) { return $found.FullName }
  }
  return $null
}

function Resolve-DefaultTargets {
  $targets = @()
  $exe = Join-Path $Root "dist\Spindle\Spindle.exe"
  if (Test-Path $exe) { $targets += $exe }
  $installerDir = Join-Path $Root "dist\installer"
  if (Test-Path $installerDir) {
    $targets += @(Get-ChildItem -Path $installerDir -Filter *.exe -File | ForEach-Object { $_.FullName })
  }
  return $targets
}

if (-not $Path -or $Path.Count -eq 0) {
  $Path = Resolve-DefaultTargets
}
if (-not $Path -or $Path.Count -eq 0) {
  throw "No executables to sign. Build first (BUILD_WINDOWS_EXE.bat) or pass -Path."
}

$missing = @($Path | Where-Object { -not (Test-Path $_) })
if ($missing.Count -gt 0) {
  throw "File(s) not found:`n  $($missing -join "`n  ")"
}

if (-not $PfxPath) {
  $PfxPath = $env:SPINDLE_CODESIGN_PFX
  if (-not $PfxPath) { $PfxPath = $env:WINDOWS_CERT_PFX }
  if (-not $PfxPath) { $PfxPath = Join-Path $Root "certs\spindle-dev-codesign.pfx" }
}
if (-not (Test-Path $PfxPath)) {
  throw @"
PFX not found: $PfxPath

Create a local cert first:
  powershell -ExecutionPolicy Bypass -File scripts\create_local_codesign_cert.ps1

Or set SPINDLE_CODESIGN_PFX to your commercial .pfx path.
"@
}

if (-not $PfxPassword) {
  $PfxPassword = $env:SPINDLE_CODESIGN_PASSWORD
  if (-not $PfxPassword) { $PfxPassword = $env:WINDOWS_CERT_PASSWORD }
  if (-not $PfxPassword) {
    $passwordFile = Join-Path $Root "certs\spindle-dev-codesign.password.txt"
    if (Test-Path $passwordFile) {
      $PfxPassword = (Get-Content -Raw $passwordFile).Trim()
    }
  }
}
if (-not $PfxPassword) {
  throw "No PFX password. Set SPINDLE_CODESIGN_PASSWORD or create certs\spindle-dev-codesign.password.txt"
}

$signtool = Find-SignTool
if (-not $signtool) {
  throw @"
signtool.exe not found.

Install one of:
  - Windows 10/11 SDK (Signing Tools feature)
  - Visual Studio Build Tools (Desktop development with C++)

Then re-run this script.
"@
}

Write-Host "Using signtool: $signtool"
Write-Host "Using PFX:      $PfxPath"
Write-Host ""

foreach ($file in $Path) {
  Write-Host "Signing $file"
  $args = @(
    "sign",
    "/f", $PfxPath,
    "/p", $PfxPassword,
    "/fd", "sha256",
    "/td", "sha256",
    "/v",
    $file
  )
  if (-not $SkipTimestamp) {
    $args = @(
      "sign",
      "/f", $PfxPath,
      "/p", $PfxPassword,
      "/fd", "sha256",
      "/tr", $TimestampUrl,
      "/td", "sha256",
      "/v",
      $file
    )
  }
  & $signtool @args
  if ($LASTEXITCODE -ne 0) {
    throw "signtool sign failed for $file (exit $LASTEXITCODE)"
  }

  Write-Host "Verifying $file"
  & $signtool verify /pa /v $file
  if ($LASTEXITCODE -ne 0) {
    throw "signtool verify failed for $file (exit $LASTEXITCODE)"
  }
  Write-Host ""
}

Write-Host "Done. Signed $($Path.Count) file(s)."
Write-Host "If Smart App Control still blocks Spindle.exe, see docs\CODE_SIGNING.md"
