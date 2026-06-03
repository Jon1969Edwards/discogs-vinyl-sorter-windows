# Mobile parity

The Expo/React Native port lives in **[discogs-vinyl-sorter-mobile](https://github.com/your-org/discogs-vinyl-sorter-mobile)** (sibling repo). Windows `core/` and the Auto-Sort GUI are the reference implementation.

Implementation status, file mapping, OAuth callbacks, test commands, and the Windows commit SHA used for validation are documented in the mobile repo:

**[MOBILE_PARITY_HANDOFF.md](https://github.com/your-org/discogs-vinyl-sorter-mobile/blob/main/MOBILE_PARITY_HANDOFF.md)**

When changing sorting, format filters, or export behavior here, update the TypeScript `src/domain/` port and Jest golden tests in the mobile repo in the same change session when possible.

**Reference commit:** `43141fcaaa671d89de17126937e2ffcc5c3cb179`
