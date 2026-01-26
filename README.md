# Discogs 33⅓ LP Shelf Sorter

This script connects to the Discogs API with your Personal Access Token, downloads your collection, filters to 33⅓ RPM Vinyl LPs, sorts them by Artist → Title → Year (with article stripping and Discogs numeric suffix cleanup), and outputs both a printable TXT and a CSV.

## Prerequisites

- Python 3.9+
- A Discogs Personal Access Token
  - Discogs → Settings → Developers → Personal Access Tokens → Generate new token

## Setup

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Provide your token either via environment variable or CLI flag:

- Environment: `DISCOGS_TOKEN` (you can use a `.env` file if you have `python-dotenv` installed)
- CLI: `--token <your_token>`

Optionally create a `.env` file:

```
DISCOGS_TOKEN=your_token_here
```

## Run

```bash
python discogs_app.py --user-agent "VinylSorter/1.0 (you@example.com)"
```

Outputs:
- `vinyl_shelf_order.txt` — printable shelf order
- `vinyl_shelf_order.csv` — spreadsheet-friendly

### Optional GUI

Prefer a window instead of CLI? Launch the Tkinter GUI (no extra dependencies):

```bash
./.venv/bin/python gui_app.py
```

Features: set per-page / max-pages, enable last-name-first (with band-safe), dividers, alignment, JSON export, and view a live log. "Open Output" opens the target directory. Leave the token blank if `DISCOGS_TOKEN` is already set (env or `.env`).

GUI prerequisites:
- Your Python must include Tk support. On macOS, the python.org installer ships with Tk. Homebrew Python often lacks it by default.
- Quick check:
  ```bash
  python - <<'PY'
  import _tkinter; print('Tk linked OK')
  PY
  ```
- If it fails, either install Python from python.org and recreate the venv using that interpreter, or install `tcl-tk` via Homebrew and recreate your environment.

### Auto-Sort GUI (watch for new additions)

If you want the shelf order to update automatically as you add items to Discogs, use the auto-sort GUI:

```bash
./.venv/bin/python autosort_gui.py
```

What it does:
- Polls your Discogs collection item count every N seconds.
- When the count changes, it rebuilds the shelf order and shows it in the app.
- Use **“Export TXT/CSV”** to write `vinyl_shelf_order.txt` and `vinyl_shelf_order.csv` to the chosen Output Dir (and `vinyl_shelf_order.json` if “Also JSON” is checked).
- Use **“Print…”** to send the current shelf order to your default printer (via `lpr`).
- Provides a **“Refresh Now”** button to force an immediate inventory check + rebuild.

No-terminal launch (macOS):
- Double-click `LaunchAutoSortGUI.command`.

Tip: to avoid entering your token each time, set `DISCOGS_TOKEN` in your environment (or create a `.env` file in the project directory).

## Customization

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

Insert letter dividers in TXT output:
```bash
python discogs_app.py --dividers
```

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

Last-name-first (conservative heuristic – only flips simple two-word personal names like "David Bowie" -> "Bowie, David"):
```bash
python discogs_app.py --last-name-first
```

Aligned columns and country code:
```bash
python discogs_app.py --txt-align --show-country
```

Extended last-name-first controls:
```bash
# Allow certain 3-word names where middle is an initial or language particle (e.g. "John Lee Hooker", "Ludwig van Beethoven")
python discogs_app.py --last-name-first --lnf-allow-3

# Exclude specific names from flipping (semicolon-separated, case-insensitive)
python discogs_app.py --last-name-first --lnf-exclude "fine young cannibals;red hot chili peppers"

# Avoid flipping obvious band-like two-word names (plural nouns / ensemble terms)
python discogs_app.py --last-name-first --lnf-safe-bands

GUI equivalents: checkboxes map directly (LP strict, Debug stats, Last-name-first, LNF allow 3, LNF safe bands, Dividers, TXT align, Show country, Also JSON). The "LNF exclude" field accepts semicolon-separated names.
Additional GUI checkboxes: "Include 45s" and "Include CDs" produce their respective files and (if JSON is also checked) contribute to the combined `all_media_shelf_order.json`.
```

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
- `--debug-stats` helps diagnose filtering by showing how many releases passed each stage.
- The app retries transient API errors (HTTP 429/5xx) a few times with short backoff and honors `Retry-After` when provided.
- Be mindful of Discogs API rate limits; the script sleeps briefly when remaining calls are low.

## Future Ideas

- A/B/C shelf divider output.
- Export JSON for downstream tooling.
- Optional exclusion of specific countries or labels.
