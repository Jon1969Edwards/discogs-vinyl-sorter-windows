# UI/UX Improvements – Implementation Guide

**Status: All items below are ✓ implemented.**

---

## Quick wins (priority)

### 1. Search placeholder ✓
- `placeholder_text="Search artist, title, label…"` on `_search_entry` in `_build_search_row`

### 2. Theme button label ✓
- `_update_theme_button` shows "☀️ Light" in dark mode, "🌙 Dark" in light mode (label = target mode)

### 3. Empty shelf message ✓
- `_order_empty_label` with "No albums yet. Add items to your Discogs collection or check your token and refresh."
- Shown via `_show_order_empty_state()` when no rows

### 4. Shortcuts help ✓
- `_shortcuts_btn` (⌨) in search row shows messagebox with all keyboard shortcuts

---

## Medium effort

### 5. Empty wishlist message ✓
- `_wishlist_empty_label` with "Add items to your Discogs wantlist to see them here"
- Shown when wishlist is empty in `refresh_wishlist_tree`

### 6. Search "no results" hint ✓
- `v_match.set("No matches — try a different term")` when matches == 0 and search is non-empty

### 7. Loading/first-build state ✓
- `_order_loading_label` with "Loading your collection…" shown until first `BuildResult` arrives

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

- Status bar: ✓ Fixed. `_build_status_bar` now creates the status bar at the bottom with status message, collection count, sync time, and optional total value (when prices enabled).
- All edits should preserve existing behavior; add new UI elements or messages without removing current functionality.
