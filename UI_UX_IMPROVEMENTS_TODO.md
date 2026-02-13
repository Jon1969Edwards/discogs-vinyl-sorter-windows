# UI/UX Improvements – Implementation Guide

**Handoff for next agent.** Implement these changes in `autosort_gui.py`.

---

## Quick wins (priority)

### 1. Search placeholder
- **File:** `autosort_gui.py`
- **Location:** `_build_search_row` – where `_search_entry` is created (~line 2082)
- **Change:** Add `placeholder_text="Search artist, title, label…"` to the `ctk.CTkEntry` constructor
- CTkEntry supports `placeholder_text` parameter

### 2. Theme button label
- **File:** `autosort_gui.py`
- **Location:** `_set_theme_colors` (~line 3265) and `_update_theme_button` (~line 3276)
- **Change:** Button text should describe the *action* (what you switch *to*):
  - In dark mode → show `"☀️ Light"` (click to switch to light)
  - In light mode → show `"🌙 Dark"` (click to switch to dark)
- Currently it shows "Dark" when dark, "Light" when light – invert so the label = target mode

### 3. Empty shelf message
- **File:** `autosort_gui.py`
- **Location:** `_render_order` (~line 3561) – when `not result.rows_sorted`
- **Change:** Instead of just clearing and showing "0 items", display a placeholder message in the treeview area, e.g. overlay or single row:  
  `"No albums yet. Add items to your Discogs collection or check your token and refresh."`
- Alternative: Add an empty-state label that is shown/hidden based on whether `_tree_rows` is empty

### 4. Shortcuts help
- **File:** `autosort_gui.py`
- **Location:** Near the header (~line 1884) or search row
- **Change:** Add a small "?" or "⌨" button that shows a tooltip or popup with:
  - Ctrl+F: Focus search
  - F5 / Ctrl+R: Refresh
  - Ctrl+S: Export
  - Ctrl+P: Print
  - Ctrl+Q: Stop/Quit
  - Ctrl+D: Toggle theme
  - Alt+Up/Down: Move item (manual order mode)
- Can use existing `ToolTip` class or `messagebox.showinfo` for a simple popup

---

## Medium effort

### 5. Empty wishlist message
- **File:** `autosort_gui.py`
- **Location:** `_setup_wishlist_tree_events` → `refresh_wishlist_tree`, or when `wishlist_data` is empty
- **Change:** When wishlist has no items, show message:  
  `"Add items to your Discogs wantlist to see them here"`

### 6. Search "no results" hint
- **File:** `autosort_gui.py`
- **Location:** `_highlight_search` or `_find_and_highlight_matches` – when `matches == 0` and `q` is non-empty
- **Change:** When there are 0 matches, consider updating the match label to e.g.  
  `"No matches — try a different term"` instead of just `"0 matches"`

### 7. Loading/first-build state
- **File:** `autosort_gui.py`
- **Location:** Before first `BuildResult` arrives – e.g. in `_render_order` or when `_last_result` is None
- **Change:** Show "Loading your collection…" or similar until the first build completes

---

## Reference info

- **Main UI build:** `_build_ui` → `_build_header`, `_build_settings_panel`, `_build_main_content`, `_build_notebook`
- **Search entry:** `self._search_entry` in `_build_search_row`
- **Theme toggle:** `self.theme_btn`, `_toggle_theme`, `_set_theme_colors`
- **Treeview:** `self.order_tree` for shelf order; cleared in `_clear_treeview`
- **ToolTip class:** Already exists (~line 902); usage example at ~line 2327
- **Keyboard shortcuts:** `_setup_keyboard_shortcuts` (~line 2898)

---

## Notes

- Status bar (`_status_bar`, `_status_label`, etc.) is referenced in `_update_status_bar_widgets` but may not be created in the UI build – verify and fix if the status bar is missing.
- All edits should preserve existing behavior; add new UI elements or messages without removing current functionality.
