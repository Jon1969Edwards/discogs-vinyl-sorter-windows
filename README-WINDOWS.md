# Discogs Vinyl Sorter - Windows Edition

Windows-compatible version of the Discogs 33⅓ LP Shelf Sorter.

## Quick Start (Windows)

### 1. Initial Setup

Double-click **SETUP.bat** to:
- Create a Python virtual environment (.venv)
- Install all required dependencies
- Prepare the app for use

### 2. Run the GUI

**Option A: Discogs Collection GUI** (Main Interface)
- Double-click **LaunchDiscogsGUI.bat**
- Enter your Discogs token and preferences
- Click "Fetch & Sort" to generate your shelf order

**Option B: Auto-Sort GUI** (Background Monitoring)
- Double-click **LaunchAutoSortGUI.bat**
- Monitors your collection and auto-regenerates shelf order when it changes

### 3. Command Line Usage

```batch
REM Activate virtual environment
.venv\Scripts\activate

REM Run with token from environment variable
set DISCOGS_TOKEN=your_token_here
python discogs_app.py --user-agent "VinylSorter/1.0 (you@example.com)"

REM Or pass token directly
python discogs_app.py --token your_token_here --dividers --json
```

## Requirements

- **Windows 10 or 11**
- **Python 3.9+** (from [python.org](https://www.python.org/downloads/))
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
- `--dividers`: Add alphabetical dividers in output
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
- `gui_app.py` - Tkinter GUI wrapper
- `autosort_gui.py` - Auto-monitoring GUI
- `demo_sort_preview.py` - Preview sorting behavior
- `test_sorting.py` - Unit tests
- `requirements.txt` - Python dependencies
- `LaunchDiscogsGUI.bat` - Windows launcher for main GUI
- `LaunchAutoSortGUI.bat` - Windows launcher for auto-sort GUI
- `SETUP.bat` - Windows setup script
- `README.md` - Full documentation (cross-platform)

## Support

For detailed documentation, see [README.md](README.md) (the full cross-platform guide).

For issues or questions, check the project repository.

---

**Windows-Specific Notes:**
- Batch files (`.bat`) replace the macOS `.command` launchers
- Virtual environment is at `.venv\Scripts\` (Windows) vs `.venv/bin/` (Unix)
- Paths use backslashes `\` on Windows but the Python code handles this automatically
