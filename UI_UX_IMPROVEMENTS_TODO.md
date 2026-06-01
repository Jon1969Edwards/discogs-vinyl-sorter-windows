# Discogs Vinyl Sorter – Implementation Plan

Work through one item at a time. Product backlog below; refactor/tech items are tracked separately.

---

## Phase 1: Foundation & Auth

| # | Task | Scope | Status |
|---|------|-------|--------|
| 1 | **Clarify auth setup** | README: PAT vs OAuth, callback URL | Done |
| 2 | **Add `.env.example`** | Placeholders for token / user-agent | Done |

---

## Phase 2: README "Future Ideas"

| # | Task | Scope | Status |
|---|------|-------|--------|
| 3 | **A/B/C shelf dividers** | Extend `--dividers` logic | Pending |
| 4 | **Country/label exclusion** | `--exclude-countries`, `--exclude-labels` | Pending |

---

## Phase 3: UX & Polish

| # | Task | Scope | Status |
|---|------|-------|--------|
| 5 | **First-run auth check** | Prompt when no token/OAuth on launch | Pending |
| 6 | **Install/shortcut improvements** | SETUP.bat, CREATE-SHORTCUTS.bat | Pending |
| 6b | **Multi-format collection filter** | Settings checkboxes; `core/format_filter.py` | Done |
| 6c | **Scrollable settings panel** | Full-width formats section (`CTkScrollableFrame`) | Done |

---

## Phase 4: Quality & Distribution

| # | Task | Scope | Status |
|---|------|-------|--------|
| 7 | **Tests for sorting** | `test_sorting.py` (heuristics); expand coverage | Partial |
| 7b | **Tests for format filter** | `test_format_filter.py` | Done |
| 8 | **Windows folder build** | `BUILD_WINDOWS_EXE.bat` + PyInstaller hidden imports | Done |
| 8b | **OAuth in shipped build** | `core/discogs_oauth_secrets.py` + hidden-import | Done (requires local secrets file) |

---

## Refactor & technical debt (incremental)

| Item | Status |
|------|--------|
| `core/build_service.py` — build/cache out of GUI | Done |
| `core/format_filter.py` + `gui/settings_panel.py` | Done |
| Remove legacy `gui_app.py` | Done |
| Unify `collect_lp` / `collect_45` / `collect_cd` on `collect_all_rows` where possible | Done |
| GUI: direct `core.api` / `core.export` imports (not `discogs_app as core`) | Done |
| GUI splits: thumbnails, shelf order tree, wishlist tab | Done |
| Further splits (header, album popup, drag/reorder handlers) | Optional / later |

---

## Progress log

- **2025-02-14:** Tasks 1 & 2 — README auth section, `.env.example`.
- **2026:** OAuth sign-in, multi-format filter, settings scroll fix, PyInstaller build script.
- **2026:** Incremental refactor — `format_filter`, `settings_panel`, `build_service`, format tests.
- **2026:** Technical follow-ups — collector wrappers, GUI module splits, cleaner imports.
