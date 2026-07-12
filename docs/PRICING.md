# Pro pricing (v1.0.0)

## Model

One-time **Pro unlock** (recommended **$19–29 USD**).

## Payment provider (MVP)

Use [Lemon Squeezy](https://www.lemonsqueezy.com) or Gumroad:

1. Create a digital product “Vinyl Shelf Sorter Pro”
2. Set `PURCHASE_URL` in `core/version.py` to your checkout link
3. Deliver license keys manually or via Lemon Squeezy license keys API (v2)

## License keys

Offline HMAC-signed format: `VSS1-…`

Generate for sales or beta:

```bash
python scripts/generate_license_key.py --email customer@example.com
```

Set `VSS_LICENSE_SECRET` in CI release builds (GitHub secret) so only your builds validate keys.

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
