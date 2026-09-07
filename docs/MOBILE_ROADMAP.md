# Mobile companion — Phase 2

Windows Pro revenue validates demand before heavy mobile monetization investment.
Mobile now supports the **same `VSS1-…` Pro license keys** as desktop (paste activation).

See [MOBILE_PARITY.md](MOBILE_PARITY.md) and the mobile repo `MOBILE_PARITY_HANDOFF.md`.

## Planned sync (Pro)

- [x] Manual shelf order (gated)
- [x] Marketplace prices (gated)
- [x] Free 100-record cap
- [x] A/B/C shelf dividers (gated)
- [ ] Wishlist marketplace availability flags (gate ready; UI TBD)

## Licensing

Same Pro license key unlocks Windows and mobile. Optional store / IAP bundle TBD.
Set `VSS_LICENSE_SECRET` (EAS secret or `.env`) to match Windows; release builds fail closed without a secret.

## Engineering

Keep sorting rules in Windows `core/` as the shared contract; mobile ports domain logic to TypeScript under `src/domain/`.
