# Spindle

**Spindle** connects to your [Discogs](https://www.discogs.com) collection, filters to the formats you care about (33⅓ RPM LPs by default), sorts them for physical shelving (Artist → Title → Year, with article stripping and Discogs suffix cleanup), and exports printable shelf lists.

The **Auto-Sort GUI** is the recommended way to use the app: sign in with Discogs, watch your collection for changes, search and browse with cover art, and export TXT, CSV, or JSON. A full **CLI** is available for scripting and one-shot runs.

> Not affiliated with Discogs. See [TERMS.md](TERMS.md) and [PRIVACY.md](PRIVACY.md).

## Quick start

**Windows (recommended):** see [README-WINDOWS.md](README-WINDOWS.md) — run `SETUP.bat`, then `LaunchAutoSortGUI.bat`. Optional: build a standalone `.exe` with `BUILD_WINDOWS_EXE.bat`.

**From source (any OS with Python 3.9+):**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python autosort_gui.py
```

On first launch, use **Sign in with Discogs** in Settings (OAuth), or paste a Personal Access Token under Advanced. See [OAUTH_SETUP.md](OAUTH_SETUP.md).

## Features

| | Free | Pro |
|---|------|-----|
| Collection sort + export | Up to **100 records** | **Unlimited** |
| Search, album info, Discogs links | ✓ | ✓ |
| Auto-watch collection changes | ✓ | ✓ |
| Letter dividers in TXT export | ✓ | ✓ |
| Marketplace prices | — | ✓ |
| Wishlist marketplace availability check | — | ✓ |
| Manual drag-and-drop shelf order | — | ✓ |
| Audio preview (Discogs samples) | — | ✓ |
| A/B/C physical shelf dividers in export | — | ✓ |

Activate Pro in **Settings → Pro License**. Details: [docs/PRICING.md](docs/PRICING.md).

On Windows, user data (config, caches, wishlist, thumbnails) lives under `%LOCALAPPDATA%\Spindle\` — not next to the `.exe`. See [PRIVACY.md](PRIVACY.md).

### Auto-Sort GUI highlights

- **Sign in with Discogs** (OAuth) or Personal Access Token
- Auto-watch: regenerates shelf order when your collection changes
- Export **TXT / CSV / JSON**, print, optional aligned columns and country codes
- Album thumbnails, search/filter, sort by artist / title / year / price
- **Wishlist** tab synced from your Discogs wantlist; check marketplace availability (Pro)
- **Manual order mode**: drag rows to match your physical shelves (Pro)
- **Audio preview** for selected releases (Pro)
- Include **45 RPM singles** and **CDs** as separate exports
- First-run wizard, dark/light theme, update checker, diagnostics export

Launch:

```bash
# Windows
LaunchAutoSortGUI.bat

# macOS / Linux (from activated venv)
python autosort_gui.py
```

Tip: set `DISCOGS_TOKEN` in a `.env` file (copy from `.env.example`) to skip re-entering a token for CLI use.

## Authentication

| Method | Use case | Variables |
|--------|----------|-----------|
| **OAuth** | Auto-Sort GUI “Sign in” (browser flow) | `DISCOGS_CONSUMER_KEY`, `DISCOGS_CONSUMER_SECRET` (or bundled in release builds; see [OAUTH_SETUP.md](OAUTH_SETUP.md)) |
| **Personal Access Token (PAT)** | CLI, GUI Advanced settings | `DISCOGS_TOKEN` |

- **OAuth**: Discogs → Settings → Developers → Create Application (callback `http://127.0.0.1:8765/callback`). Put credentials in `.env`, or copy `core/discogs_oauth_secrets.example.py` to `core/discogs_oauth_secrets.py` (gitignored).
- **PAT**: Discogs → Settings → Developers → Personal Access Tokens → Generate. Set `DISCOGS_TOKEN` or pass `--token <your_token>` to the CLI.

## CLI usage

```bash
python discogs_app.py --user-agent "Spindle/1.0 (you@example.com)"
```

Outputs:

- `vinyl_shelf_order.txt` — printable shelf order
- `vinyl_shelf_order.csv` — spreadsheet-friendly
- `vinyl_shelf_order.json` — optional, with `--json`

### Customization

Push Various Artists to the end:

```bash
python discogs_app.py --various-policy last
```

Add extra leading articles to strip (French/Spanish/German/etc.):

```bash
python discogs_app.py --articles-extra "le,la,les,el,los,las,der,die,das"
```

Choose an output directory:

```bash
python discogs_app.py --output-dir ./out
```

Version and banner:

```bash
python discogs_app.py --version
```

Show debug stats and/or enforce explicit RPM:

```bash
# Print counts of scanned items and how many matched Vinyl/LP/33RPM
python discogs_app.py --debug-stats

# Require explicit 33 RPM in format descriptions (stricter filtering)
python discogs_app.py --lp-strict
```

Insert letter dividers in TXT output (`=== A ===` between artists):

```bash
python discogs_app.py --dividers
```

Insert **A/B/C shelf** dividers for physical shelf units (`=== SHELF A (A–H) ===`, etc.):

```bash
python discogs_app.py --abc-dividers
```

Shelf ranges: **A** = A–H (and non-alpha), **B** = I–P, **C** = Q–Z. The Auto-Sort GUI offers the same options under Settings → **TXT shelf dividers** (A/B/C dividers require Pro).

Also write JSON alongside TXT/CSV:

```bash
python discogs_app.py --json
```

Include additional media categories (7" 45 RPM singles and CDs) with separate outputs:

```bash
# 45 RPM singles only
python discogs_app.py --include-45s

# CDs only
python discogs_app.py --include-cds

# Both, plus JSON (generates combined all_media_shelf_order.json)
python discogs_app.py --include-45s --include-cds --json
```

When enabled:

- LP files: `vinyl_shelf_order.txt`, `vinyl_shelf_order.csv`, optional `vinyl_shelf_order.json`
- 45 RPM files: `vinyl45_shelf_order.txt`, `vinyl45_shelf_order.csv`, optional `vinyl45_shelf_order.json`
- CD files: `cd_shelf_order.txt`, `cd_shelf_order.csv`, optional `cd_shelf_order.json`
- Combined JSON (only if `--json` and at least one extra category selected): `all_media_shelf_order.json` with a `media_type` field (`LP`, `45`, or `CD`).

List items worth at least a given Discogs lowest_price (in SEK) in a separate file:

```bash
# Anything with lowest_price >= 500 SEK
python discogs_app.py --valuable-sek 500
```

Creates `valuable_over_500kr.txt` containing shelf-order lines with an appended approximate price (e.g. `[~750 SEK]`). Notes:

- Uses Discogs `lowest_price` (may be None if not available).
- Fetches each release individually; large collections will take extra time.
- Prices reflect the moment of querying and may change; treat as rough guidance.

Last-name-first (conservative heuristic – only flips simple two-word personal names like "David Bowie" → "Bowie, David"):

```bash
python discogs_app.py --last-name-first
```

Aligned columns and country code:

```bash
python discogs_app.py --txt-align --show-country
```

Extended last-name-first controls:

```bash
# Allow certain 3-word names where middle is an initial or language particle
python discogs_app.py --last-name-first --lnf-allow-3

# Exclude specific names from flipping (semicolon-separated, case-insensitive)
python discogs_app.py --last-name-first --lnf-exclude "fine young cannibals;red hot chili peppers"

# Avoid flipping obvious band-like two-word names (plural nouns / ensemble terms)
python discogs_app.py --last-name-first --lnf-safe-bands
```

GUI equivalents: checkboxes map directly (LP strict, Debug stats, Last-name-first, LNF allow 3, LNF safe bands, Dividers, TXT align, Show country, Also JSON). The "LNF exclude" field accepts semicolon-separated names. Additional GUI checkboxes: "Include 45s" and "Include CDs" produce their respective files and (if JSON is also checked) contribute to the combined `all_media_shelf_order.json`.

Cap number of pages (safety / testing):

```bash
python discogs_app.py --max-pages 3
```

Change per-page (max 100):

```bash
python discogs_app.py --per-page 50
```

## Notes

- `/oauth/identity` is used to infer your username from the token before paging folder `0`.
- LP detection defaults to permissive: any Vinyl format with `LP` or `Album` counts (RPM optional). Use `--lp-strict` to require a `33 RPM` description.
- Sorting removes leading articles (The/A/An plus extras you provide) and strips Discogs numeric suffixes like `(2)`.
- For shelf order, **`Name and the …`** / **`Name & the …`** (e.g. Elvis Costello and the Attractions) is grouped with **solo `Name`**; release lines still show Discogs’ full artist credits.
- `--debug-stats` helps diagnose filtering by showing how many releases passed each stage.
- The app retries transient API errors (HTTP 429/5xx) a few times with short backoff and honors `Retry-After` when provided.
- Be mindful of Discogs API rate limits; the script sleeps briefly when remaining calls are low.

## Documentation

| Doc | Description |
|-----|-------------|
| [README-WINDOWS.md](README-WINDOWS.md) | Windows quick start, `.exe` build, troubleshooting |
| [docs/CODE_SIGNING.md](docs/CODE_SIGNING.md) | Local and release Authenticode signing |
| [OAUTH_SETUP.md](OAUTH_SETUP.md) | OAuth sign-in for users and developers |
| [docs/PRICING.md](docs/PRICING.md) | Free vs Pro, licensing |
| [docs/RELEASE.md](docs/RELEASE.md) | Production release checklist (secrets, signing, store) |
| [docs/CODE_SIGNING.md](docs/CODE_SIGNING.md) | Local and release Authenticode signing |
| [docs/SUPPORT.md](docs/SUPPORT.md) | Common issues, diagnostics |
| [docs/BETA.md](docs/BETA.md) | Beta testing guide |
| [PRIVACY.md](PRIVACY.md) | Privacy policy |
| [TERMS.md](TERMS.md) | Terms of use |

## Roadmap

Planned or under consideration:

- Shelf position numbers in exports (sequential `#001`, `#002`, … for physical lookup)
- Highlight new acquisitions since last export
- Duplicate / variant detection (same master, different pressings)
- Optional exclusion filters by country or label
- Mobile companion sync (see [docs/MOBILE_ROADMAP.md](docs/MOBILE_ROADMAP.md))
