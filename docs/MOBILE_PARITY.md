# Mobile parity

The Expo/React Native port is **Spindle** (mobile), sibling repo
[discogs-vinyl-sorter-mobile](https://github.com/Jon1969Edwards/discogs-vinyl-sorter-mobile).
Windows `core/` and the Auto-Sort GUI are the reference implementation.

Full status, file mapping, OAuth callbacks, branding notes, and the Windows
commit SHA used for validation: see **`MOBILE_PARITY_HANDOFF.md`** in that repo.

When changing sorting, format filters, or export behavior here, update the
TypeScript `src/domain/` port and Jest golden tests in the mobile repo in the
same change session when possible.
