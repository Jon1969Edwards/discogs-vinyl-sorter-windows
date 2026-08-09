#Requires -Version 5.1
<#
.SYNOPSIS
  Create a local self-signed Authenticode certificate for Spindle development.

.DESCRIPTION
  Generates a Code Signing certificate, exports a PFX under certs\ (gitignored),
  and trusts it for the current Windows user (Root + TrustedPeople).

  This removes "Unknown publisher" friction on THIS PC and lets you practice the
  same sign/verify workflow used for release builds.

  Note: Windows Smart App Control may still block self-signed apps. For SAC and
  public distribution you need a commercially trusted code-signing certificate.
  See docs/CODE_SIGNING.md.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\create_local_codesign_cert.ps1
#>
[CmdletBinding()]
param(
  [string]$Subject = "CN=Spindle Dev Code Signing",
  [string]$CertsDir = "",
  [string]$PfxPassword = "",
  [int]$YearsValid = 5
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $CertsDir) {
  $CertsDir = Join-Path $Root "certs"
}

New-Item -ItemType Directory -Force -Path $CertsDir | Out-Null
$PfxPath = Join-Path $CertsDir "spindle-dev-codesign.pfx"
$CerPath = Join-Path $CertsDir "spindle-dev-codesign.cer"
$PasswordFile = Join-Path $CertsDir "spindle-dev-codesign.password.txt"

if (-not $PfxPassword) {
  if (Test-Path $PasswordFile) {
    $PfxPassword = (Get-Content -Raw $PasswordFile).Trim()
  } else {
    # Random local-only password; kept next to the PFX (both gitignored).
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $PfxPassword = [Convert]::ToBase64String($bytes)
    Set-Content -Path $PasswordFile -Value $PfxPassword -Encoding ascii
  }
}

$securePassword = ConvertTo-SecureString -String $PfxPassword -Force -AsPlainText

Write-Host "Creating self-signed code-signing certificate..."
Write-Host "  Subject: $Subject"

# Remove previous Spindle Dev certs from CurrentUser stores so re-runs stay clean.
$stores = @("Cert:\CurrentUser\My", "Cert:\CurrentUser\Root", "Cert:\CurrentUser\TrustedPeople")
foreach ($storePath in $stores) {
  Get-ChildItem $storePath -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -eq $Subject } |
    ForEach-Object {
      Write-Host "Removing existing cert from $storePath ($($_.Thumbprint))"
      Remove-Item $_.PSPath -Force
    }
}

$cert = New-SelfSignedCertificate `
  -Type CodeSigningCert `
  -Subject $Subject `
  -KeyAlgorithm RSA `
  -KeyLength 2048 `
  -HashAlgorithm SHA256 `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -KeyExportPolicy Exportable `
  -NotAfter (Get-Date).AddYears($YearsValid) `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")

Export-PfxCertificate -Cert $cert -FilePath $PfxPath -Password $securePassword | Out-Null
Export-Certificate -Cert $cert -FilePath $CerPath -Type CERT | Out-Null

# Trust for Authenticode verification on this user account.
Import-Certificate -FilePath $CerPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
Import-Certificate -FilePath $CerPath -CertStoreLocation "Cert:\CurrentUser\TrustedPeople" | Out-Null

Write-Host ""
Write-Host "Local code-signing certificate ready."
Write-Host "  PFX:        $PfxPath"
Write-Host "  CER:        $CerPath"
Write-Host "  Thumbprint: $($cert.Thumbprint)"
Write-Host "  Password:   $PasswordFile"
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Build:  BUILD_WINDOWS_EXE.bat"
Write-Host "  2. Sign:   powershell -ExecutionPolicy Bypass -File scripts\sign_windows_exe.ps1"
Write-Host "  Or rebuild - BUILD_WINDOWS_EXE.bat signs automatically when the PFX exists."
Write-Host ""
Write-Host "See docs\CODE_SIGNING.md for Smart App Control and release signing."
