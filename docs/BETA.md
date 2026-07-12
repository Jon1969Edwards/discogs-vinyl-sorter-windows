# Beta launch guide

## Goals

- 20–50 collectors complete sign-in and a full refresh without support
- Median load acceptable at 200+ records (with price cache)
- Zero P0 bugs (launch crash, auth loop, data loss)

## Beta Pro keys

Generate keys for testers:

```bash
python scripts/generate_license_key.py --email tester@example.com
```

Share keys privately. Testers activate via **Help → Activate Pro license** or **Settings → Pro License**.

## Feedback

- In-app: **Help → Send feedback**
- GitHub Issues (if public repo)
- Email: support contact in `core/version.py`

## Update checker

Ship `release/version.json` on each tag. The app checks this from **Help → Check for updates**.

## Diagnostics

**Help → Export diagnostics** creates a zip with redacted config and optional `crash.log`.
