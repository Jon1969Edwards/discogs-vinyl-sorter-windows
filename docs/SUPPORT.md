# Support

## Contact

Email: `support@example.com` (update in `core/version.py` for production)

Include:

- App version (**Help → About**)
- Windows version
- Steps to reproduce
- Optional: **Help → Export diagnostics** zip

## Common issues

### Sign-in fails

- Use the official installer (OAuth credentials are bundled at build time)
- Check firewall allows localhost callback on port 8765

### Prices show “Pro feature”

- Activate a Pro license in **Settings → Pro License**
- Free tier does not fetch marketplace prices

### Collection truncated at 100 records

- Free tier limit; upgrade to Pro for full collection display and export

### Audio preview unavailable

- Pro feature; requires **pygame** (installed automatically on Python 3.12)
- On Python 3.13+, pygame may fail to install — use Python 3.12 and re-run **SETUP.bat**, or run: `pip install -r requirements-audio.txt`

## Not affiliated with Discogs

For Discogs account or marketplace issues, contact Discogs support directly.
