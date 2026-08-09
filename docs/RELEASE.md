# Release checklist (production)

Use this before tagging `v1.0.0` and charging for Pro.

## 1. GitHub Actions secrets

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|--------|----------|---------|
| `DISCOGS_CONSUMER_KEY` | Yes | Bundled OAuth for Sign in with Discogs |
| `DISCOGS_CONSUMER_SECRET` | Yes | Bundled OAuth |
| `VSS_LICENSE_SECRET` | Yes | HMAC secret baked into the installer (long random string; **not** the public default) |
| `WINDOWS_CERT_BASE64` | Yes for public PC downloads | Base64-encoded Authenticode `.pfx` |
| `WINDOWS_CERT_PASSWORD` | With cert | PFX password |

Generate a license secret (PowerShell):

```powershell
[Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
```

Store it only in GitHub Actions and your password manager. Keys signed with the old public default **will not** work in release builds.

## 2. Store / Buy Pro URL

1. Create a Lemon Squeezy or Gumroad product “Spindle Pro”.
2. Set `PURCHASE_URL` in [`core/version.py`](../core/version.py) to the checkout link (or bake via env in a future step).
3. Deliver keys with:

```powershell
$env:VSS_LICENSE_SECRET = "<same secret as CI>"
.venv\Scripts\python scripts\generate_license_key.py --email customer@example.com
```

Until the store is live, **Buy Pro** opens GitHub Releases.

## 3. Discogs commercial notice

Customize and send [`DISCOGS_COMMERCIAL_EMAIL.md`](DISCOGS_COMMERCIAL_EMAIL.md) to Discogs developer support **before** charging.

## 4. Code signing

Buy an OV/EV Authenticode certificate. See [`CODE_SIGNING.md`](CODE_SIGNING.md). Unsigned installers are blocked by Smart App Control for many customers.

## 5. Tag and ship

```powershell
git tag v1.0.0
git push origin v1.0.0
```

Confirm the Release workflow:

- OAuth + license bake succeed
- Signed `Spindle-Setup-1.0.0.exe` is uploaded
- Clean PC: install → Sign in → activate a key generated with `VSS_LICENSE_SECRET`

## 6. Post-release

- Update [`release/version.json`](../release/version.json) on `main` if the download URL or notes change
- Closed beta goals: [`BETA.md`](BETA.md)
