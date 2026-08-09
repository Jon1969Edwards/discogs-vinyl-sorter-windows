# Pro pricing (v1.0.0)

## Model

One-time **Pro unlock** — **$24 USD** (recommended list price).

## Payment provider

1. Create a digital product “Spindle Pro” on [Lemon Squeezy](https://www.lemonsqueezy.com) or Gumroad
2. Set `PURCHASE_URL` in `core/version.py` to your checkout link
3. Deliver license keys manually or via your store’s license-key integration:

```bash
# Use the SAME VSS_LICENSE_SECRET as GitHub Actions release builds
python scripts/generate_license_key.py --email customer@example.com
```

See [RELEASE.md](RELEASE.md) for baking `VSS_LICENSE_SECRET` into installers.

## Free tier

- Collection sort + export (100 records)
- Basic search, album info, Discogs links

## Pro tier

- Unlimited collection
- Marketplace prices + cache
- Wishlist availability check
- Manual shelf order
- Audio preview
- A/B/C shelf dividers in export
