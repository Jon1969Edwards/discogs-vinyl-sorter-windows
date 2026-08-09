# Mobile parity

The Expo/React Native port lives in a sibling **discogs-vinyl-sorter-mobile** repo when published. Windows `core/` and the Auto-Sort GUI are the reference implementation.

Implementation status, file mapping, OAuth callbacks, test commands, and the Windows commit SHA used for validation are documented in the mobile repo when available.

When changing sorting, format filters, or export behavior here, update the TypeScript `src/domain/` port and Jest golden tests in the mobile repo in the same change session when possible.
