# Spindle — Windows

Windows build of **Spindle**: sort your Discogs vinyl collection for physical shelves and export printable lists. Full cross-platform docs: [README.md](README.md).

## Quick Start (Windows)

### 1. Initial Setup

Double-click **SETUP.bat** to:
- Create a Python virtual environment (.venv)
- Install all required dependencies
- Prepare the app for use

### 2. Enable sign-in (one-time)

Double-click **SETUP_OAUTH.bat** to register the app with Discogs (callback `http://127.0.0.1:8765/callback`). You only do this once per install/build.

### 3. Run the GUI

Double-click **LaunchAutoSortGUI.bat** to open the Auto-Sort GUI (recommended). It watches your collection, supports browser sign-in (OAuth), and exports shelf order as TXT, CSV, or JSON. You can also run `.venv\Scripts\python autosort_gui.py`.

**Free tier** covers sort and export for up to 100 records. **Pro** unlocks unlimited collection size, marketplace prices, wishlist availability checks, manual shelf order, audio preview, and A/B/C shelf dividers. See [docs/PRICING.md](docs/PRICING.md).

For a one-shot fetch without the Auto-Sort window, use the command line (see below) or run `python discogs_app.py` with your token.

**Desktop shortcut:** Right-click `LaunchAutoSortGUI.bat` → Send to → Desktop (create shortcut).

### Optional: build a real Windows app (`.exe`)

To get a normal program you can pin to the taskbar or Start menu (no `.bat`):

1. Run **SETUP.bat** once so `.venv` exists.
2. Double-click **BUILD_WINDOWS_EXE.bat** (installs PyInstaller if needed, then builds).
3. Run **`dist\Spindle\Spindle.exe`**.

**Build failed with "Access is denied" on `dist\Spindle`?** Close any running copy of `Spindle.exe`, close File Explorer windows inside `dist\`, then run **BUILD_WINDOWS_EXE.bat** again. The script now stops the app and retries cleanup automatically.

Put your **`.env`** file in **the same folder as** `Spindle.exe` if you use one (OAuth consumer key/secret, token, etc.). Config and cache files from the app are stored next to that `.exe` as well.

### 3. Command Line Usage

```batch
REM Activate virtual environment
.venv\Scripts\activate

REM Run with token from environment variable
set DISCOGS_TOKEN=your_token_here
python discogs_app.py --user-agent "Spindle/1.0 (you@example.com)"

REM Or pass token directly
python discogs_app.py --token your_token_here --dividers --json
```

## Requirements

- **Windows 10 or 11**
- **Python 3.12 recommended** (3.9–3.12 supported for full features). Python 3.13+ may not install **pygame** (Pro audio preview) until prebuilt wheels exist.
  - **Important**: During installation, check "Add Python to PATH"
  - The standard installer includes Tkinter (required for GUI)

## Getting Your Discogs Token

1. Log in to [Discogs](https://www.discogs.com)
2. Go to Settings → Developers
3. Generate a new Personal Access Token
4. Copy the token and use it in the GUI or CLI

## Output Files

The app generates these files in your chosen output directory:
- **vinyl_shelf_order.txt** - Human-readable shelf order
- **vinyl_shelf_order.csv** - Spreadsheet-compatible format
- **vinyl_shelf_order.json** (optional) - Machine-readable format

## Common Options

### Last-Name-First Sorting
Add `--last-name-first` to sort artists by last name (e.g., "Davis, Miles")
- `--lnf-safe-bands`: Prevents flipping obvious band names
- `--lnf-allow-3`: Also flip 3-word names
- `--lnf-exclude "Artist1,Artist2"`: Exclude specific artists from flipping

### Filter Options
- `--lp-strict`: Strict 33⅓ LP detection (excludes 10" and box sets)
- `--include-45s`: Include 7" 45 RPM singles
- `--include-cds`: Include CDs

### Output Options
- `--dividers`: Add alphabetical dividers in TXT (`=== A ===`)
- `--abc-dividers`: Add A/B/C shelf section dividers (A: A–H, B: I–P, C: Q–Z)
- `--txt-align`: Align columns in text output
- `--show-country`: Include country in output
- `--json`: Also generate JSON output

### Debugging
- `--debug-stats`: Show filtering statistics
- `--max-pages N`: Limit API requests (for testing)

## Troubleshooting

### "Python not found"
- Install Python from python.org
- Ensure "Add Python to PATH" was checked during installation
- Restart Command Prompt or PowerShell after installation

### "Tk error" or GUI won't start
- The official python.org installer includes Tkinter by default
- If using a custom Python distribution, you may need to reinstall with Tk support

### Virtual environment issues
- Delete the `.venv` folder
- Run **SETUP.bat** again

## Files Included

- `discogs_app.py` - Main CLI application
- `autosort_gui.py` - Auto-Sort GUI (recommended)
- `setup_oauth.py` / `SETUP_OAUTH.bat` - One-time OAuth setup for browser sign-in
- `test_sorting.py` - Sorting unit tests (`python test_sorting.py`)
- `test_format_filter.py` - Format detection/filter tests (`python test_format_filter.py`)
- `requirements.txt` - Python dependencies
- `LaunchAutoSortGUI.bat` - Windows launcher for the Auto-Sort GUI
- `BUILD_WINDOWS_EXE.bat` - Optional: build `Spindle.exe` (PyInstaller)
- `SETUP.bat` - Windows setup script
- `README.md` - Full documentation (cross-platform)

## Support

| Doc | Description |
|-----|-------------|
| [README.md](README.md) | Full feature list and CLI reference |
| [OAUTH_SETUP.md](OAUTH_SETUP.md) | OAuth sign-in setup |
| [docs/PRICING.md](docs/PRICING.md) | Free vs Pro |
| [docs/SUPPORT.md](docs/SUPPORT.md) | Common issues, diagnostics export |
| [PRIVACY.md](PRIVACY.md) | Privacy policy |
| [TERMS.md](TERMS.md) | Terms of use |

---

**Windows-Specific Notes:**
- Batch files (`.bat`) replace the macOS `.command` launchers
- Virtual environment is at `.venv\Scripts\` (Windows) vs `.venv/bin/` (Unix)
- Paths use backslashes `\` on Windows but the Python code handles this automatically
