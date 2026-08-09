# Beta launch guide

## Goals

- 20–50 collectors complete sign-in and a full refresh without support
- Median load acceptable at 200+ records (with price cache)
- Zero P0 bugs (launch crash, auth loop, data loss)

## Beta Pro keys

Generate keys with the **same** `VSS_LICENSE_SECRET` used in release CI (see [RELEASE.md](RELEASE.md)):

```bash
# PowerShell
$env:VSS_LICENSE_SECRET = "<secret>"
python scripts/generate_license_key.py --email tester@example.com
```

Share keys privately. Testers activate via **Help → Activate Pro license** or **Settings → Pro License**.

## Feedback

- In-app: **Help → Send feedback**
- GitHub Issues: https://github.com/Jon1969Edwards/discogs-vinyl-sorter-windows/issues
- Email: jon1969edwards@gmail.com

## Update checker

Ship `release/version.json` on each tag. The app checks this from **Help → Check for updates**.

## Diagnostics

**Help → Export diagnostics** creates a zip with redacted config and optional `crash.log`.
