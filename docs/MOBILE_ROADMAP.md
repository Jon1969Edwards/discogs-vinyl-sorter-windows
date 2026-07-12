# Mobile companion — Phase 2

Windows Pro revenue validates demand before mobile investment.

See [MOBILE_PARITY.md](MOBILE_PARITY.md) for feature scope.

## Planned sync (Pro)

- Manual shelf order
- Wishlist marketplace availability flags

## Not in scope for mobile v1

- Full Discogs collection re-host
- Price fetch on mobile (optional later)

## Licensing

Same Pro license key can unlock mobile when shipped; optional subscription bundle TBD.

## Engineering

Keep sorting rules in `core/` as the shared contract; mobile app ports domain logic to Kotlin/Swift or Flutter.
