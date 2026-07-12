# Privacy Policy

**Last updated:** 2026-03-22

**Spindle** ("the app") is a desktop application that helps you organize
your personal Discogs vinyl collection. This app is **not affiliated with, endorsed by,
or sponsored by Discogs**.

## What we collect

**We do not operate servers that receive your collection data.** By default, everything
stays on your computer:

| Data | Where stored | Purpose |
|------|----------------|---------|
| Discogs OAuth tokens | `.discogs_config.json` next to the app | Sign in and access your collection |
| Collection / price cache | `.discogs_collection_cache.json` | Faster reloads |
| Manual shelf order | `.discogs_manual_order.json` | Your custom sort order |
| Wishlist | `wishlist.json` | Local wishlist and availability checks |
| Thumbnail cache | `.discogs_thumbnails/` | Album artwork |
| License key (Pro) | `.discogs_config.json` | Unlock Pro features offline |
| Settings | `.discogs_config.json` | Preferences |

Tokens are obfuscated on disk but are not a substitute for full encryption. Protect
your computer user account like you would for any app that stores API credentials.

## What leaves your device

When you use the app, it contacts:

- **Discogs API** — to load your collection, wishlist, and marketplace prices (per your sign-in)
- **iTunes / Deezer** — to find 30-second audio preview URLs (artist + album search only)
- **Spotify** — only if you click "Search on Spotify" (opens your browser)
- **YouTube** — only if you click a Discogs-linked video preview (opens your browser)

Optional **update check** (Help → Check for updates) fetches a small `version.json`
file from our release URL to compare version numbers. No personal data is sent.

Optional **Send feedback** opens your email client; you choose what to send.

Optional **Export diagnostics** creates a local zip with app version, OS info, and
redacted config (tokens removed). You choose whether to share it.

## Telemetry

We do **not** embed analytics or crash reporting that phones home automatically in v1.
If you opt in to diagnostics export, you control what is shared.

## Children

The app is not directed at children under 13.

## Changes

We may update this policy. Continued use after changes constitutes acceptance.

## Contact

For privacy questions, use the support contact listed in the app (Help → About) or
your purchase receipt from Gumroad / Lemon Squeezy.
