# Code signing (Windows)

Spindle’s PyInstaller build (`dist\Spindle\Spindle.exe`) must be **Authenticode-signed** before Windows will treat it as a trustworthy app. Unsigned builds often trip **Smart App Control** and SmartScreen.

## Local development (self-signed)

Use this on your own PC so you can practice the same sign/verify flow as release builds.

### 1. One-time: create and trust a local certificate

Double-click **`SETUP_LOCAL_CODESIGN.bat`**, or:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\create_local_codesign_cert.ps1
```

This creates (gitignored):

| File | Purpose |
|------|---------|
| `certs\spindle-dev-codesign.pfx` | Private key + cert for `signtool` |
| `certs\spindle-dev-codesign.cer` | Public cert |
| `certs\spindle-dev-codesign.password.txt` | Local PFX password |

The public cert is imported into **CurrentUser** `Root` and `TrustedPeople` so Windows on *this* account can verify the signature.

### 2. Install `signtool` (Windows SDK)

`signtool.exe` ships with the [Windows 10/11 SDK](https://developer.microsoft.com/windows/downloads/windows-sdk/). In the installer, enable **Signing Tools for Windows SDK** (or install Visual Studio Build Tools with the C++ desktop workload).

Confirm:

```powershell
Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe |
  Where-Object { $_.FullName -match '\\x64\\' } |
  Select-Object -First 1 FullName
```

### 3. Build and sign

```powershell
.\BUILD_WINDOWS_EXE.bat
```

If `certs\spindle-dev-codesign.pfx` exists, the build script signs automatically.

Or sign an existing build:

```powershell
.\SIGN_WINDOWS.bat
# or:
powershell -ExecutionPolicy Bypass -File scripts\sign_windows_exe.ps1
```

Verify:

```powershell
signtool verify /pa /v .\dist\Spindle\Spindle.exe
```

### Smart App Control caveat

**Self-signed certificates are often still blocked by Smart App Control**, which expects signatures that chain to a Microsoft-trusted CA.

| Situation | What to expect |
|-----------|----------------|
| Local self-signed, SAC on | May still be blocked |
| Local self-signed, SAC off / Evaluation allowing | “Unknown publisher” should improve once cert is trusted |
| Commercial OV/EV code-signing cert | Required for SAC-friendly and public distribution |
| Daily development | Prefer `LaunchAutoSortGUI.bat` (no `.exe`, no SAC issue) |

Do **not** turn Smart App Control off solely to ship an unsigned app to others. Fix signing instead.

## Distribution (commercially trusted certificate)

1. Buy an **Authenticode / code-signing** certificate (OV or EV) from a CA in the Microsoft Trusted Root Program (DigiCert, Sectigo, SSL.com, etc.).
2. Export a `.pfx` (or use a hardware token / cloud HSM — follow your CA’s process).
3. Sign locally:

```powershell
$env:SPINDLE_CODESIGN_PFX = "C:\secure\spindle-release.pfx"
$env:SPINDLE_CODESIGN_PASSWORD = "…"
powershell -ExecutionPolicy Bypass -File scripts\sign_windows_exe.ps1
```

4. Or configure GitHub Actions secrets (already wired in `.github/workflows/release.yml`):

| Secret | Meaning |
|--------|---------|
| `WINDOWS_CERT_BASE64` | Base64-encoded `.pfx` |
| `WINDOWS_CERT_PASSWORD` | PFX password |

CI signs `dist\Spindle\*.exe` and the Inno Setup installer when those secrets are set.

Timestamping uses DigiCert’s server (`http://timestamp.digicert.com`) so signatures remain valid after the cert expires.

Full production checklist (OAuth, license bake, store, Discogs notice, tag): [`RELEASE.md`](RELEASE.md).

## Security notes

- Never commit `certs\`, `.pfx`, or password files (already covered by `.gitignore`).
- Local self-signed trust is **per user / per machine** — other PCs will not trust it.
- Rotate or delete the local cert when finished testing: Certificate Manager (`certmgr.msc`) → Personal / Trusted Root / Trusted People → remove `CN=Spindle Dev Code Signing`.
