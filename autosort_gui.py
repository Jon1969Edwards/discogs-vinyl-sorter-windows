"""Discogs Auto-Sort GUI

Watches your Discogs collection, regenerates shelf order on changes, and exports
printable lists. Sign in with Discogs via OAuth in Settings.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from core.paths import project_root

# Load .env from project folder before discogs_app / OAuth (cwd may differ e.g. IDE, shortcuts)
try:
  from dotenv import load_dotenv  # type: ignore

  load_dotenv(project_root() / ".env")
except Exception:
  pass

# Use CustomTkinter for modern UI
import customtkinter as ctk
from tkinter import StringVar, BooleanVar, IntVar, filedialog, messagebox, Tk
import tkinter as tk
from tkinter import ttk  # Keep ttk for Treeview (no CTk replacement yet)

from core.api import discogs_headers
from core.export import generate_txt_lines, write_csv, write_json, write_txt
from core.models import ReleaseRow, BuildResult
from gui.spinning_record import SpinningRecord
from gui.thumbnails import ImagePreviewPopup, ThumbnailCache
from gui.tooltip import ToolTip
from core.build_service import (
  AutoConfig,
  CollectionCache,
  build_once,
  get_collection_count,
  _get_user_headers,
)
from core.config_store import MANUAL_ORDER_FILE, load_config, save_config
from core.feature_gate import (
  FREE_RECORD_LIMIT,
  apply_record_limit,
  can_check_wishlist_availability,
  can_fetch_prices,
  can_use_abc_dividers,
  can_use_manual_order,
  upgrade_message,
)
from core.licensing import is_pro, license_summary
from core.version import APP_NAME, __version__
from core.format_filter import (
  FORMAT_FILTERS,
  filter_rows_by_format,
  parse_saved_formats,
)
from gui.constants import (
  DIVIDER_MODE_BY_LABEL,
  DIVIDER_MODE_LABELS,
  FONT_2XL,
  FONT_LG,
  FONT_MD,
  FONT_SEGOE_UI,
  FONT_SEGOE_UI_SEMIBOLD,
  FONT_SM,
  FONT_XL,
  FONT_XS,
  POLL_SECONDS_DEFAULT,
)

DEFAULT_USER_AGENT = "Mozilla/5.0"

# Button style constants
SECONDARY_TBUTTON_STYLE = "Secondary.TButton"


class ManualOrderManager:
  """Manages user's custom manual ordering of their collection.
  
  Stores release IDs in the user's preferred order, allowing drag-and-drop
  reordering that persists across sessions.
  """
  
  def __init__(self, order_file: Path = MANUAL_ORDER_FILE):
    self.order_file = order_file
    self._data: dict = {
      "version": 1,
      "username": None,
      "order": [],  # List of release_ids in manual order
      "enabled": False,  # Whether manual ordering is active
    }
    self._load()
  
  def _load(self) -> None:
    """Load manual order from disk."""
    try:
      if self.order_file.exists():
        with self.order_file.open("r", encoding="utf-8") as f:
          loaded = json.load(f)
          if loaded.get("version") == 1:
            self._data = loaded
    except Exception:
      pass
  
  def _save(self) -> None:
    """Save manual order to disk."""
    try:
      with self.order_file.open("w", encoding="utf-8") as f:
        json.dump(self._data, f, indent=2)
    except Exception:
      pass
  
  def get_username(self) -> str | None:
    """Get the username this order belongs to."""
    return self._data.get("username")
  
  def set_username(self, username: str) -> None:
    """Set username and clear order if changed."""
    if self._data.get("username") != username:
      self._data = {
        "version": 1,
        "username": username,
        "order": [],
        "enabled": False,
      }
      self._save()
  
  def is_enabled(self) -> bool:
    """Check if manual ordering is enabled."""
    return self._data.get("enabled", False)
  
  def set_enabled(self, enabled: bool) -> None:
    """Enable or disable manual ordering."""
    self._data["enabled"] = enabled
    self._save()
  
  def get_order(self) -> list[int]:
    """Get the list of release IDs in manual order."""
    return self._data.get("order", [])
  
  def set_order(self, release_ids: list[int]) -> None:
    """Set the manual order."""
    self._data["order"] = release_ids
    self._data["enabled"] = True
    self._save()
  
  def apply_order(self, rows: list[ReleaseRow]) -> list[ReleaseRow]:
    """Apply manual ordering to a list of rows.
    
    Returns rows reordered according to manual order.
    New items (not in manual order) are appended at the end.
    """
    if not self.is_enabled():
      return rows
    
    order = self.get_order()
    if not order:
      return rows
    
    # Create lookup by release_id
    row_by_id = {r.release_id: r for r in rows if r.release_id}
    
    # Build ordered list
    ordered = []
    seen_ids = set()
    
    # Add items in manual order
    for rid in order:
      if rid in row_by_id and rid not in seen_ids:
        ordered.append(row_by_id[rid])
        seen_ids.add(rid)
    
    # Append any new items not in manual order
    for row in rows:
      if row.release_id and row.release_id not in seen_ids:
        ordered.append(row)
        seen_ids.add(row.release_id)
      elif not row.release_id:
        ordered.append(row)
    
    return ordered
  
  def clear(self) -> None:
    """Clear manual order and disable."""
    self._data["order"] = []
    self._data["enabled"] = False
    self._save()
  
  def save(self) -> None:
    """Explicitly save to disk."""
    self._save()



class ProgressDialog:
  """A modal progress dialog with a spinning vinyl record animation."""

  DONE_MESSAGE = "Done!"

  def set_error(self, message: str) -> None:
    """Show error message with red highlight."""
    self.msg_label.config(text=message, fg="#ff5555")
    self.progress_label.config(text="Error", fg="#ff5555")
    self.top.configure(bg="#2e1620")
    self.title_label.config(fg="#ff5555")
    self.top.update()

  def set_done(self, message: str = None) -> None:
    """Show done message with green highlight, then close after short delay."""
    done_msg = message if message is not None else self.DONE_MESSAGE
    self.msg_label.config(text=done_msg, fg="#55ff55")
    self.progress_label.config(text=self.DONE_MESSAGE, fg="#55ff55")
    self.top.configure(bg="#162e20")
    self.title_label.config(fg="#55ff55")
    self.top.update()
    self.top.after(900, self.close)

  def __init__(self, parent, title: str = "Please Wait", message: str = "Loading..."):
    import tkinter as tk

    self.top = tk.Toplevel(parent)
    self.top.title(title)
    self.top.transient(parent)
    self.top.grab_set()
    
    # Dialog size - taller to accommodate log
    self.top.geometry("520x420")
    self.top.resizable(False, False)
    
    # Style it - modern dark theme
    self.top.configure(bg="#16213e")
    
    # Accent strip at top for visual consistency
    accent_bar = tk.Frame(self.top, bg="#6c63ff", height=4)
    accent_bar.pack(fill="x")
    
    # Title label at top (dynamic)
    self.title_label = tk.Label(
      self.top,
      text=title,
      font=(FONT_SEGOE_UI_SEMIBOLD, FONT_XL),
      bg="#16213e",
      fg="#6c63ff"
    )
    self.title_label.pack(pady=(20, 8))
    
    # Main content frame (record + info side by side)
    content_frame = tk.Frame(self.top, bg="#16213e")
    content_frame.pack(fill="x", padx=24, pady=(8, 12))
    
    # Left side: Spinning record canvas
    self._record_spinner = SpinningRecord(content_frame, size=100, bg="#16213e", accent="#6c63ff")
    self._record_spinner.pack(side="left", padx=(0, 20))
    self._record_spinner.start()
    
    # Right side: Message and progress
    info_frame = tk.Frame(content_frame, bg="#16213e")
    info_frame.pack(side="left", fill="both", expand=True)
    
    self.msg_label = tk.Label(
      info_frame,
      text=message,
      font=(FONT_SEGOE_UI, FONT_SM),
      bg="#16213e",
      fg="#eaeaea",
      wraplength=300,
      justify="left",
      anchor="w"
    )
    self.msg_label.pack(anchor="w", pady=(12, 8))
    
    self.progress_label = tk.Label(
      info_frame,
      text="Starting...",
      font=(FONT_SEGOE_UI_SEMIBOLD, FONT_LG),
      bg="#16213e",
      fg="#6c63ff"
    )
    self.progress_label.pack(anchor="w", pady=(8, 8))
    
    # Log section with header
    log_header = tk.Frame(self.top, bg="#16213e")
    log_header.pack(fill="x", padx=24, pady=(8, 4))
    log_label = tk.Label(
      log_header,
      text="Activity Log",
      font=(FONT_SEGOE_UI_SEMIBOLD, FONT_SM),
      bg="#16213e",
      fg="#8892b0"
    )
    log_label.pack(side="left")
    
    # Log text area - shows recent entries with padding
    log_container = tk.Frame(self.top, bg="#0f0f1a", bd=0)
    log_container.pack(fill="both", expand=True, padx=24, pady=(0, 20))
    
    self.log_text = tk.Text(
      log_container,
      height=8,
      width=50,
      font=("Cascadia Code", FONT_XS),
      bg="#0f0f1a",
      fg="#8892b0",
      relief="flat",
      wrap="word",
      state="disabled",
      padx=10,
      pady=10,
      insertbackground="#6c63ff"
    )
    self.log_text.pack(fill="both", expand=True)
    
    # Prevent closing
    self.top.protocol("WM_DELETE_WINDOW", lambda: None)
    
    # Center on parent
    self.top.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.top.winfo_width() // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.top.winfo_height() // 2)
    self.top.geometry(f"+{x}+{y}")
  
  def update_message(self, message: str) -> None:
    """Update the main message."""
    self.msg_label.config(text=message)
    self.top.update()
  
  def update_progress(self, progress: str) -> None:
    """Update the progress text and add to log."""
    self.progress_label.config(text=progress)
    self.add_log(progress)
    self.top.update()
  
  def add_log(self, entry: str) -> None:
    """Add an entry to the log display."""
    try:
      self.log_text.config(state="normal")
      self.log_text.insert("end", entry + "\n")
      self.log_text.see("end")  # Auto-scroll to bottom
      self.log_text.config(state="disabled")
    except Exception:
      pass
  
  def close(self) -> None:
    """Close the dialog."""
    try:
      self._record_spinner.stop()
      self.top.grab_release()
      self.top.destroy()
    except Exception:
      pass




from gui.order_panel import OrderPanel
from gui.settings_panel import SettingsPanel
from gui.wishlist_panel import WishlistPanel


class App:
  # Track hover state for wishlist
  _wishlist_hover_release_id: int | None = None

  def _on_wishlist_tree_motion(self, event):
    """Handle mouse motion over the wishlist treeview for album artwork preview."""
    if not self._thumbnails_enabled or not self._image_preview:
      return

    def hide_preview():
      if self._image_preview and self._wishlist_hover_release_id is not None:
        self._image_preview.hide(delay=50)
        self._wishlist_hover_release_id = None

    region = self.wishlist_tree.identify_region(event.x, event.y)
    column = self.wishlist_tree.identify_column(event.x)

    # Only show preview when hovering the image column (#0 or tree region)
    if column != "#0" and region != "tree":
      hide_preview()
      return

    item = self.wishlist_tree.identify_row(event.y)
    if not item:
      hide_preview()
      return

    try:
      idx = self.wishlist_tree.index(item)
      if idx < 0 or idx >= len(self._wishlist_rows):
        return

      row = self._wishlist_rows[idx]
      if not row.release_id or row.release_id == self._wishlist_hover_release_id:
        return

      self._wishlist_hover_release_id = row.release_id

      try:
        headers = discogs_headers(self.v_token.get(), self.v_user_agent.get())
      except Exception:
        headers = {"User-Agent": DEFAULT_USER_AGENT}

      screen_x = event.x_root
      screen_y = event.y_root
      cover_url = getattr(row, 'cover_image_url', '') or getattr(row, 'thumb_url', '')
      self._image_preview.show(row.release_id, cover_url, headers, screen_x, screen_y)
    except Exception as e:
      print(f"Wishlist hover error: {e}")

  def _on_wishlist_tree_leave(self, event):
    """Handle mouse leaving the wishlist treeview."""
    if self._image_preview:
      self._image_preview.hide()
    self._wishlist_hover_release_id = None

  def _set_action_buttons_state(self, state: str) -> None:
    """Enable or disable main action buttons (refresh, export, print) during refresh."""
    for btn in [getattr(self, '_refresh_btn', None), getattr(self, '_export_btn', None), getattr(self, '_print_btn', None)]:
      if btn is not None:
        try:
          btn.config(state=state)
        except Exception:
          pass

  def __init__(self, root: Tk) -> None:
    self.root = root
    root.title(f"{APP_NAME} {__version__}")
    try:
      root.minsize(900, 650)
    except Exception:
      pass

    # Dark mode toggle
    self.v_dark_mode = BooleanVar(value=True)

    # CustomTkinter handles theming automatically
    # We only need ttk.Style for Treeview widget (no CTk replacement yet)
    self.style = ttk.Style()

    # Palette (best-effort; note: macOS may still use native button chrome)
    self._dark_colors = {
      "bg": "#0a0e1a",        # VERY dark background (like Employee Hub)
      "panel": "#1e293b",     # Elevated card color (brighter for contrast)
      "panel2": "#0f1419",    # Even darker for main area background
      "text": "#f1f5f9",      # Brighter text for better contrast
      "muted": "#94a3b8",     # Lighter muted color
      "accent": "#6c63ff",    # purple accent
      "accent2": "#00d9ff",   # cyan accent
      "accent3": "#ff6b6b",   # coral/red accent
      "success": "#10b981",   # Brighter green
      "warn": "#ffab00",      # amber
      "order_bg": "#1e293b",  # Match panel for consistency
      "order_fg": "#f1f5f9",  # Brighter text
      "button_bg": "#6c63ff", # purple button
      "button_fg": "#ffffff", # white text
      "button_hover": "#5a52d5", # darker purple on hover
      "border": "#334155",    # More visible border (lighter)
      "shadow": "#000000",    # Pure black shadow
      "card_border": "#475569", # Even lighter border for cards
    }
    self._light_colors = {
      "bg": "#f0f4f8",        # light blue-gray
      "panel": "#ffffff",     # white - for cards
      "panel2": "#e8eef4",    # light gray-blue - for background
      "text": "#1a1a2e",      # dark text
      "muted": "#64748b",     # muted gray
      "accent": "#6c63ff",    # purple accent
      "accent2": "#0891b2",   # teal accent
      "accent3": "#e11d48",   # rose accent
      "success": "#16a34a",   # green
      "warn": "#d97706",      # amber
      "order_bg": "#ffffff",  # white for table cells
      "order_fg": "#1a1a2e",  # dark text
      "button_bg": "#6c63ff", # purple button
      "button_fg": "#ffffff", # white text
      "button_hover": "#5a52d5", # darker purple on hover
      "border": "#cbd5e1",    # visible border color
      "shadow": "#94a3b8",    # shadow for depth
      "card_border": "#94a3b8", # Card border for light mode
    }
    self._colors = self._dark_colors.copy()

    # Configure custom styles
    self._configure_styles()

    # Load saved configuration
    saved_cfg = load_config()

    self.v_token = StringVar(value=saved_cfg.get("token", ""))
    self._oauth_access_token = saved_cfg.get("oauth_access_token") or ""
    self._oauth_access_secret = saved_cfg.get("oauth_access_secret") or ""
    self.v_user_agent = StringVar(value=saved_cfg.get("user_agent", "VinylSorter/1.0 (+contact)"))
    self.v_output_dir = StringVar(value=saved_cfg.get("output_dir", str(Path.cwd())))
    self.v_per_page = IntVar(value=saved_cfg.get("per_page", 100))
    self.v_json = BooleanVar(value=saved_cfg.get("write_json", False))
    _divider_mode = saved_cfg.get("divider_mode", "none")
    if _divider_mode not in DIVIDER_MODE_LABELS:
      _divider_mode = "none"
    self.v_divider_mode = StringVar(value=DIVIDER_MODE_LABELS[_divider_mode])
    self.v_poll = IntVar(value=saved_cfg.get("poll_seconds", POLL_SECONDS_DEFAULT))
    # Always start with prices OFF - user must enable during session
    self.v_show_prices = BooleanVar(value=False)
    self.v_currency = StringVar(value=saved_cfg.get("currency", "USD"))
    self.v_sort_by = StringVar(value=saved_cfg.get("sort_by", "artist"))

    # Format filter checkboxes. Restore saved selection or fall back to default.
    saved_formats = parse_saved_formats(saved_cfg.get("formats"))
    self.v_formats = {
      key: BooleanVar(value=(key in saved_formats)) for key, _label in FORMAT_FILTERS
    }
    
    # Initialize the collection cache
    self._collection_cache = CollectionCache()
    
    # Initialize the manual order manager
    self._manual_order = ManualOrderManager()
    self.v_manual_order_enabled = BooleanVar(value=self._manual_order.is_enabled())
    
    # Initialize thumbnail cache and preview popup
    self._thumbnail_cache = ThumbnailCache()
    self._thumbnails_enabled = self._thumbnail_cache.is_available()
    self._image_preview: ImagePreviewPopup | None = None  # Created after UI setup

    # Auto-save settings when they change
    self.v_token.trace_add("write", lambda *_: self._save_settings())
    self.v_user_agent.trace_add("write", lambda *_: self._save_settings())
    self.v_output_dir.trace_add("write", lambda *_: self._save_settings())
    self.v_json.trace_add("write", lambda *_: self._save_settings())
    self.v_divider_mode.trace_add("write", lambda *_: self._save_settings())
    self.v_poll.trace_add("write", lambda *_: self._save_settings())
    self.v_show_prices.trace_add("write", lambda *_: self._on_show_prices_change())
    self.v_currency.trace_add("write", lambda *_: self._save_settings())
    self.v_sort_by.trace_add("write", lambda *_: self._save_settings())
    for _fvar in self.v_formats.values():
      _fvar.trace_add("write", lambda *_: self._on_format_filter_change())

    self.v_search = StringVar(value="")
    self.v_match = StringVar(value="")
    self.v_status = StringVar(value="Starting…")
    
    # Status bar info
    self.v_collection_count = StringVar(value="")
    self.v_last_sync = StringVar(value="")
    self.v_total_value = StringVar(value="")

    # Holds the most recent build for export/printing
    self._last_result: BuildResult | None = None
    self.result_q: queue.Queue[BuildResult] = queue.Queue()

    self._stop = threading.Event()
    self._wake = threading.Event()

    self._last_count: int | None = None
    self._last_built_at: float | None = None
    self._force_rebuild: bool = False

    self.log_q: queue.Queue[str] = queue.Queue()
    
    # Progress dialog control - messages from background thread
    self.progress_q: queue.Queue[tuple] = queue.Queue()
    self._progress_dialog: ProgressDialog | None = None
    
    # Drag-and-drop state
    self._drag_start_index: int | None = None
    self._drag_item_id: str | None = None

    self._auth_prompt_shown = False

    self._worker_cfg_lock = threading.Lock()
    self._worker_cfg: AutoConfig | None = None
    self._loading_elapsed_job: str | None = None
    self._loading_base_message = ""
    self._loading_last_fraction: float | None = None

    self._record_limit_truncated = False

    self._build_ui(root)
    self._setup_keyboard_shortcuts()
    self._pump_queues()
    self.root.after(0, self._apply_startup_window_state)

    # First-run wizard, then optional sign-in prompt
    self.root.after(500, self._prompt_first_run_auth)
    self.root.after(600, self._update_pro_ui)

    # Snapshot settings before the watcher reads them (StringVar is main-thread only).
    self._refresh_worker_cfg()

    # Start watching immediately
    threading.Thread(target=self._watch_loop, daemon=True).start()

  def _configure_styles(self) -> None:
    """Configure custom ttk styles for a modern, professional look."""
    c = self._colors
    
    # Always configure Treeview style (needed for shelf order list)
    self._configure_treeview_style()

    # Standard ttk styling
    try:
      if "clam" in self.style.theme_names():
        self.style.theme_use("clam")
    except Exception:
      pass
    
    # Main frame styles
    self.style.configure("App.TFrame", background=c["panel2"])
    self.style.configure("TFrame", background=c["panel"])
    
    # Label styles - refined typography
    self.style.configure("TLabel", 
                         background=c["panel"], 
                         foreground=c["text"],
                         font=(FONT_SEGOE_UI, FONT_SM))
    self.style.configure("Header.TLabel",
                         background=c["bg"],
                         foreground=c["text"],
                         font=(FONT_SEGOE_UI_SEMIBOLD, FONT_2XL))
    self.style.configure("Subtitle.TLabel",
                         background=c["bg"],
                         foreground=c["muted"],
                         font=(FONT_SEGOE_UI, FONT_MD))
    
    # Card/LabelFrame styles - enhanced with visible borders
    self.style.configure("Card.TLabelframe",
                         background=c["panel"],
                         bordercolor=c["border"],
                         lightcolor=c["border"],
                         darkcolor=c["border"],
                         relief="solid",
                         borderwidth=2)
    self.style.configure("Card.TLabelframe.Label",
                         foreground=c["accent"],
                         background=c["panel"],
                         font=(FONT_SEGOE_UI_SEMIBOLD, FONT_MD))
    
    # Primary button style - enhanced with subtle border for depth
    PRIMARY_TBUTTON_STYLE = "Primary.TButton"
    self.style.configure(PRIMARY_TBUTTON_STYLE,
                         background=c["accent"],
                         foreground=c["button_fg"],
                         borderwidth=1,
                         bordercolor=c["accent2"],
                         focuscolor=c["accent"],
                         lightcolor=c["accent"],
                         darkcolor=c["button_hover"],
                         relief="raised",
                         padding=(20, 12),
                         font=(FONT_SEGOE_UI_SEMIBOLD, FONT_SM))
    self.style.map(PRIMARY_TBUTTON_STYLE,
                   background=[("active", c["button_hover"]), ("pressed", c["button_hover"]), ("disabled", c["muted"])],
                   foreground=[("active", c["button_fg"]), ("disabled", "#888888")],
                   relief=[("pressed", "sunken")])
    
    # Success button style (green) - enhanced with depth
    SUCCESS_TBUTTON_STYLE = "Success.TButton"
    self.style.configure(SUCCESS_TBUTTON_STYLE,
                         background=c["success"],
                         foreground="#ffffff",
                         borderwidth=1,
                         bordercolor="#00e65a",
                         lightcolor=c["success"],
                         darkcolor="#00a844",
                         relief="raised",
                         padding=(20, 12),
                         font=(FONT_SEGOE_UI_SEMIBOLD, FONT_SM))
    self.style.map(SUCCESS_TBUTTON_STYLE,
                   background=[("active", "#00a844"), ("pressed", "#00a844")],
                   relief=[("pressed", "sunken")])
    
    # Secondary button style - subtle with border
    SECONDARY_TBUTTON_STYLE = "Secondary.TButton"
    self.style.configure(SECONDARY_TBUTTON_STYLE,
                         background=c["panel2"],
                         foreground=c["text"],
                         borderwidth=1,
                         bordercolor=c["muted"],
                         lightcolor=c["panel2"],
                         darkcolor=c["order_bg"],
                         relief="raised",
                         padding=(16, 10),
                         font=(FONT_SEGOE_UI, FONT_SM))
    self.style.map(SECONDARY_TBUTTON_STYLE,
                   background=[("active", c["order_bg"])],
                   relief=[("pressed", "sunken")])
    
    # Danger button style (red) - enhanced with depth
    DANGER_TBUTTON_STYLE = "Danger.TButton"
    self.style.configure(DANGER_TBUTTON_STYLE,
                         background=c["accent3"],
                         foreground="#ffffff",
                         borderwidth=1,
                         bordercolor="#ff8989",
                         lightcolor=c["accent3"],
                         darkcolor="#c41840",
                         relief="raised",
                         padding=(20, 12),
                         font=(FONT_SEGOE_UI_SEMIBOLD, FONT_SM))
    self.style.map(DANGER_TBUTTON_STYLE,
                   background=[("active", "#c41840"), ("pressed", "#c41840")],
                   relief=[("pressed", "sunken")])
    
    # Regular button - enhanced with subtle border
    self.style.configure("TButton",
                         background=c["panel2"],
                         foreground=c["text"],
                         borderwidth=1,
                         bordercolor=c["muted"],
                         lightcolor=c["panel2"],
                         darkcolor=c["order_bg"],
                         focuscolor=c["panel2"],
                         relief="raised",
                         padding=(16, 10),
                         font=(FONT_SEGOE_UI, FONT_SM))
    self.style.map("TButton",
                   background=[("active", c["order_bg"]), ("pressed", c["order_bg"])],
                   relief=[("pressed", "sunken")])
    
    # Entry style - enhanced with visible border
    self.style.configure("TEntry",
                         fieldbackground=c["order_bg"],
                         foreground=c["text"],
                         insertcolor=c["text"],
                         borderwidth=2,
                         lightcolor=c["border"],
                         darkcolor=c["border"],
                         relief="solid",
                         padding=10)
    self.style.map("TEntry",
                   fieldbackground=[("focus", c["order_bg"])],
                   lightcolor=[("focus", c["accent"])],
                   darkcolor=[("focus", c["accent"])],
                   bordercolor=[("focus", c["accent"])])
    
    # Combobox style - enhanced with visible border
    self.style.configure("TCombobox",
                         fieldbackground=c["order_bg"],
                         background=c["order_bg"],
                         foreground=c["text"],
                         arrowcolor=c["accent"],
                         borderwidth=2,
                         lightcolor=c["border"],
                         darkcolor=c["border"],
                         selectbackground=c["accent"],
                         selectforeground="#ffffff",
                         relief="solid",
                         padding=8)
    self.style.map("TCombobox",
                   fieldbackground=[("readonly", c["order_bg"]), ("focus", c["order_bg"])],
                   foreground=[("readonly", c["text"])],
                   background=[("readonly", c["order_bg"]), ("active", c["order_bg"])],
                   arrowcolor=[("active", c["accent2"])],
                   bordercolor=[("focus", c["accent"])])
    
    # Also configure the dropdown listbox via option_add
    try:
      self.root.option_add("*TCombobox*Listbox.background", c["order_bg"])
      self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
      self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
      self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
      self.root.option_add("*TCombobox*Listbox.font", (FONT_SEGOE_UI, FONT_SM))
    except Exception:
      pass
    
    # Checkbutton style - clean modern look
    self.style.configure("TCheckbutton",
                         background=c["panel"],
                         foreground=c["text"],
                         focuscolor=c["panel"],
                         font=(FONT_SEGOE_UI, FONT_SM))
    self.style.map("TCheckbutton",
                   background=[("active", c["panel"])],
                   indicatorcolor=[("selected", c["accent"]), ("!selected", c["order_bg"])])
    
    # Spinbox style - enhanced with visible border
    self.style.configure("TSpinbox",
                         fieldbackground=c["order_bg"],
                         foreground=c["text"],
                         arrowcolor=c["accent"],
                         borderwidth=2,
                         lightcolor=c["border"],
                         darkcolor=c["border"],
                         relief="solid",
                         padding=8)
    self.style.map("TSpinbox",
                   arrowcolor=[("active", c["accent2"])],
                   bordercolor=[("focus", c["accent"])])
    
    # Notebook styles - clean tabs
    self.style.configure("TNotebook",
                         background=c["panel2"],
                         borderwidth=1,
                         bordercolor=c["panel2"],
                         tabmargins=[2, 2, 2, 0])
    self.style.configure("TNotebook.Tab",
                         background=c["panel2"],
                         foreground=c["muted"],
                         padding=(24, 12),
                         borderwidth=1,
                         bordercolor=c["panel2"],
                         font=(FONT_SEGOE_UI_SEMIBOLD, FONT_SM))
    self.style.map("TNotebook.Tab",
                   background=[("selected", c["panel"])],
                   foreground=[("selected", c["accent"])],
                   bordercolor=[("selected", c["accent"])],
                   expand=[("selected", [0, 0, 0, 3])])  # Enhanced raise effect
    
    # Scrollbar style - slim modern scrollbar
    self.style.configure("TScrollbar",
                         background=c["panel"],
                         troughcolor=c["panel2"],
                         borderwidth=0,
                         arrowcolor=c["accent"],
                         width=12)
    self.style.map("TScrollbar",
                   background=[("active", c["order_bg"])])
    
    # Progressbar style
    self.style.configure("TProgressbar",
                         background=c["accent"],
                         troughcolor=c["panel2"],
                         borderwidth=0,
                         lightcolor=c["accent"],
                         darkcolor=c["accent"])
    
    # Separator style
    self.style.configure("TSeparator",
                         background=c["panel2"])
    
    # Root window background
    try:
      self.root.configure(bg=c["panel2"])
    except Exception:
      pass

  def _configure_treeview_style(self) -> None:
    """Configure Treeview widget colors for current theme."""
    c = self._colors
    
    # Configure Treeview style - use custom style name to avoid ttkbootstrap conflicts
    style_name = "Dark.Treeview" if self.v_dark_mode.get() else "Light.Treeview"
    
    self.style.configure(style_name,
                         background=c["order_bg"],
                         foreground=c["order_fg"],
                         fieldbackground=c["order_bg"],
                         borderwidth=0,
                         relief="flat",
                         rowheight=52)
    self.style.configure(f"{style_name}.Heading",
                         background=c["panel"],
                         foreground=c["text"],
                         relief="raised",
                         borderwidth=2)
    self.style.map(style_name,
                   background=[("selected", c["accent"])],
                   foreground=[("selected", "#ffffff")])
    self.style.map(f"{style_name}.Heading",
                   background=[("active", c["panel"])])
    
    # Also configure the default Treeview style
    self.style.configure("Treeview",
                         background=c["order_bg"],
                         foreground=c["order_fg"],
                         fieldbackground=c["order_bg"],
                         borderwidth=0,
                         relief="flat",
                         rowheight=52)
    self.style.configure("Treeview.Heading",
                         background=c["panel"],
                         foreground=c["text"],
                         relief="raised",
                         borderwidth=2)
    self.style.map("Treeview",
                   background=[("selected", c["accent"])],
                   foreground=[("selected", "#ffffff")])
    
    # Use option_add for more aggressive color override
    try:
      self.root.option_add("*Treeview*background", c["order_bg"])
      self.root.option_add("*Treeview*foreground", c["order_fg"])
      self.root.option_add("*Treeview*fieldBackground", c["order_bg"])
    except Exception:
      pass
    
    # Try to apply to existing treeview if it exists
    if hasattr(self, 'order_tree'):
      try:
        # Force update the treeview colors using tk options
        self.order_tree.configure(style=style_name)
      except Exception:
        pass

  def _build_ui(self, root: Tk) -> None:
    import tkinter as tk
    frm = ctk.CTkFrame(root, fg_color="transparent")
    frm.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frm.columnconfigure(0, weight=0)
    frm.columnconfigure(1, weight=1)

    row = 0
    self._build_header(frm, row)
    row += 1
    frm.rowconfigure(row, weight=1)
    self._build_settings_panel(frm, row)
    main_content = self._build_main_content(frm, row)
    self._build_notebook(main_content)
    row += 1
    self._build_status_bar(frm, row)

  def _is_window_maximized(self) -> bool:
    try:
      if sys.platform == "win32":
        return self.root.state() == "zoomed"
      return bool(self.root.attributes("-fullscreen"))
    except Exception:
      return False

  def _maximize_window(self) -> None:
    try:
      if sys.platform == "win32":
        self.root.state("zoomed")
      else:
        self.root.attributes("-fullscreen", True)
    except Exception:
      pass

  def _restore_window(self) -> None:
    try:
      if sys.platform == "win32":
        self.root.state("normal")
      else:
        self.root.attributes("-fullscreen", False)
    except Exception:
      pass

  def _toggle_window_maximize(self) -> None:
    if self._is_window_maximized():
      self._restore_window()
    else:
      self._maximize_window()
    self._update_maximize_button()

  def _update_maximize_button(self) -> None:
    btn = getattr(self, "_maximize_btn", None)
    tooltip = getattr(self, "_maximize_tooltip", None)
    if btn is None:
      return
    if self._is_window_maximized():
      btn.configure(text="❐")
      if tooltip is not None:
        tooltip.text = "Restore (F11)"
    else:
      btn.configure(text="□")
      if tooltip is not None:
        tooltip.text = "Maximize (F11)"

  def _build_header(self, frm, row):
    # Clean, minimal header
    self._header = ctk.CTkFrame(frm, fg_color="transparent")
    self._header.grid(row=row, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
    self._header.columnconfigure(0, weight=1)

    # Simple title
    self._header_title = ctk.CTkLabel(
      self._header,
      text=f"💿 {APP_NAME}",
      font=(FONT_SEGOE_UI_SEMIBOLD, FONT_2XL),
    )
    self._header_title.grid(row=0, column=0, sticky="w", padx=20, pady=(8, 4))

    self._header_subtitle = ctk.CTkLabel(
      self._header,
      text=f"v{__version__}  •  Vinyl Collection Manager  •  Export & Print",
      font=(FONT_SEGOE_UI, FONT_MD),
      text_color=self._colors["muted"],
    )
    self._header_subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))

    # Window controls (minimize, close) - needed in fullscreen when title bar is hidden
    win_ctrl = ctk.CTkFrame(self._header, fg_color="transparent")
    win_ctrl.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 8), pady=8)

    min_btn = ctk.CTkButton(
      win_ctrl,
      text="−",
      width=40,
      height=36,
      corner_radius=6,
      fg_color=self._colors["accent"],
      hover_color=self._colors["button_hover"],
      font=(FONT_SEGOE_UI, 18),
      command=lambda: self.root.iconify(),
    )
    min_btn.pack(side="left", padx=(0, 4))
    ToolTip(min_btn, "Minimize")

    self._maximize_btn = ctk.CTkButton(
      win_ctrl,
      text="□",
      width=40,
      height=36,
      corner_radius=6,
      fg_color=self._colors["accent"],
      hover_color=self._colors["button_hover"],
      font=(FONT_SEGOE_UI, 16),
      command=self._toggle_window_maximize,
    )
    self._maximize_btn.pack(side="left", padx=(0, 4))
    self._maximize_tooltip = ToolTip(self._maximize_btn, "Maximize (F11)")

    close_btn = ctk.CTkButton(
      win_ctrl,
      text="×",
      width=40,
      height=36,
      corner_radius=6,
      fg_color=self._colors["accent"],
      hover_color="#e74c3c",
      font=(FONT_SEGOE_UI, 20),
      command=lambda: self.root.destroy(),
    )
    close_btn.pack(side="left")
    ToolTip(close_btn, "Close")

    # Theme toggle button
    self.theme_btn = ctk.CTkButton(
      self._header,
      text="☀️ Light",
      command=self._toggle_theme,
      width=100,
      height=42,
      corner_radius=8,
      fg_color=self._colors["accent"],
      hover_color=self._colors["button_hover"],
    )
    self.theme_btn.grid(row=0, column=2, rowspan=2, sticky="e", padx=20, pady=8)

  def _build_status_bar(self, frm, row):
    """Build the status bar at the bottom with collection info, sync time, and optional value."""
    self._status_bar = ctk.CTkFrame(
      frm,
      height=36,
      fg_color=self._colors["accent"],
      corner_radius=0,
    )
    self._status_bar.grid(row=row, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
    self._status_bar.grid_propagate(False)
    self._status_bar.columnconfigure(0, weight=1)

    # Main status message (left)
    self._status_label = ctk.CTkLabel(
      self._status_bar,
      textvariable=self.v_status,
      font=(FONT_SEGOE_UI, FONT_SM),
      text_color="#ffffff",
    )
    self._status_label.grid(row=0, column=0, sticky="w", padx=16, pady=6)

    # Right-side info: collection count, sync time, optional value
    info_frame = ctk.CTkFrame(self._status_bar, fg_color="transparent")
    info_frame.grid(row=0, column=1, sticky="e", padx=16, pady=6)

    self._count_icon = ctk.CTkLabel(info_frame, text="💿", font=(FONT_SEGOE_UI, FONT_SM), text_color="#ffffff")
    self._count_icon.pack(side="left", padx=(0, 4))
    self._count_label = ctk.CTkLabel(
      info_frame,
      textvariable=self.v_collection_count,
      font=(FONT_SEGOE_UI, FONT_SM),
      text_color="#ffffff",
    )
    self._count_label.pack(side="left", padx=(0, 16))

    self._sync_icon = ctk.CTkLabel(info_frame, text="🕐", font=(FONT_SEGOE_UI, FONT_SM), text_color="#ffffff")
    self._sync_icon.pack(side="left", padx=(0, 4))
    self._sync_label = ctk.CTkLabel(
      info_frame,
      textvariable=self.v_last_sync,
      font=(FONT_SEGOE_UI, FONT_SM),
      text_color="#ffffff",
    )
    self._sync_label.pack(side="left", padx=(0, 16))

    self._value_sep = ctk.CTkLabel(info_frame, text="|", font=(FONT_SEGOE_UI, FONT_SM), text_color="#ffffff")
    self._value_sep.pack(side="left", padx=(0, 8))
    self._value_icon = ctk.CTkLabel(info_frame, text="💰", font=(FONT_SEGOE_UI, FONT_SM), text_color="#ffffff")
    self._value_label = ctk.CTkLabel(
      info_frame,
      textvariable=self.v_total_value,
      font=(FONT_SEGOE_UI, FONT_SM),
      text_color="#ffffff",
    )
    # Value section not packed initially; _show_value_section() shows when prices available

  def _build_settings_panel(self, frm, row):
    self._settings = SettingsPanel(self)
    self._settings.build(frm, row)

  def _build_main_content(self, frm, row):
    import tkinter as tk
    main_content = ctk.CTkFrame(frm, fg_color="transparent")
    main_content.grid(row=row, column=1, sticky="nsew", padx=(6, 12), pady=8)
    main_content.columnconfigure(0, weight=1)
    main_content.rowconfigure(3, weight=1)
    self._build_search_row(main_content)
    self._build_action_buttons(main_content)
    self._build_pro_banner(main_content)
    return main_content

  def _build_search_row(self, main_content):
    search_row = ctk.CTkFrame(main_content, fg_color="transparent")
    search_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    search_row.columnconfigure(1, weight=1)

    ctk.CTkLabel(search_row, text="🔍 Search", font=(FONT_SEGOE_UI, FONT_MD)).grid(row=0, column=0, sticky="w", padx=(0, 8))

    # Modern rounded search entry
    self._search_entry = ctk.CTkEntry(
      search_row,
      textvariable=self.v_search,
      font=(FONT_SEGOE_UI, FONT_MD),
      height=38,
      corner_radius=8,
      placeholder_text="Search artist, title, label…",
    )
    self._search_entry.grid(row=0, column=1, sticky="ew", padx=6)

    # Modern clear button
    self._clear_btn = ctk.CTkButton(
      search_row,
      text="✕ Clear",
      command=lambda: self.v_search.set(""),
      width=80,
      height=38,
      corner_radius=8,
      fg_color="#4a5568",
      hover_color="#2d3748",
    )
    self._clear_btn.grid(row=0, column=2, sticky="e", padx=6)

    ctk.CTkLabel(search_row, textvariable=self.v_match, font=(FONT_SEGOE_UI, FONT_SM)).grid(row=0, column=3, sticky="e", padx=6)

    # Shortcuts help button
    shortcuts_text = (
      "Ctrl+F: Focus search\nF5 / Ctrl+R: Refresh\nCtrl+S: Export\n"
      "Ctrl+P: Print\nCtrl+Q: Stop/Quit\nCtrl+D: Toggle theme\nAlt+Up/Down: Move item (manual order)"
    )
    self._shortcuts_btn = ctk.CTkButton(
      search_row,
      text="⌨",
      width=36,
      height=38,
      corner_radius=8,
      fg_color="#4a5568",
      hover_color="#2d3748",
      font=(FONT_SEGOE_UI, FONT_LG),
      command=lambda: messagebox.showinfo("Keyboard Shortcuts", shortcuts_text),
    )
    self._shortcuts_btn.grid(row=0, column=4, sticky="e", padx=(0, 6))
    ToolTip(self._shortcuts_btn, "Keyboard shortcuts")
    self._build_help_menu(search_row)
    self.v_search.trace_add("write", lambda *_: self._on_search_change())

  def _build_action_buttons(self, main_content):
    btn = ctk.CTkFrame(main_content, fg_color="transparent")
    btn.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    btn.columnconfigure(0, weight=1)
    btn.columnconfigure(1, weight=1)
    btn.columnconfigure(2, weight=1)
    btn.columnconfigure(3, weight=1)

    # Modern CustomTkinter buttons with color coding
    self._refresh_btn = ctk.CTkButton(
      btn, text="🔄 Refresh", command=self._refresh_now,
      corner_radius=8, height=42,
      fg_color=self._colors["accent"], hover_color=self._colors["button_hover"]
    )
    self._refresh_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)

    self._export_btn = ctk.CTkButton(
      btn, text="📁 Export", command=self._export_files,
      corner_radius=8, height=42,
      fg_color=self._colors["success"], hover_color="#00a844"
    )
    self._export_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=4)

    self._print_btn = ctk.CTkButton(
      btn, text="🖨️ Print", command=self._print_current,
      corner_radius=8, height=42,
      fg_color="#4a5568", hover_color="#2d3748"
    )
    self._print_btn.grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=4)

    self._stop_btn = ctk.CTkButton(
      btn, text="⏹️ Stop", command=self._stop_app,
      corner_radius=8, height=42,
      fg_color=self._colors["accent3"], hover_color="#c41840"
    )
    self._stop_btn.grid(row=0, column=3, sticky="ew", pady=4)

  def _build_pro_banner(self, main_content):
    self._pro_banner = ctk.CTkFrame(main_content, fg_color="#4a3728", corner_radius=8)
    self._pro_banner.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    self._pro_banner.columnconfigure(0, weight=1)
    self._pro_banner_label = ctk.CTkLabel(
      self._pro_banner,
      text="",
      font=(FONT_SEGOE_UI, FONT_SM),
      text_color="#fef3c7",
      wraplength=700,
      justify="left",
    )
    self._pro_banner_label.grid(row=0, column=0, sticky="w", padx=12, pady=8)
    self._pro_upgrade_btn = ctk.CTkButton(
      self._pro_banner,
      text="Upgrade to Pro",
      width=140,
      command=self._show_license_dialog,
      fg_color="#f59e0b",
      hover_color="#d97706",
    )
    self._pro_upgrade_btn.grid(row=0, column=1, sticky="e", padx=12, pady=8)
    self._pro_banner.grid_remove()

  def _build_help_menu(self, search_row):
    help_menu = tk.Menu(self.root, tearoff=0)
    help_menu.add_command(label="About", command=self._show_about_dialog)
    help_menu.add_command(label="Check for updates…", command=self._check_for_updates)
    help_menu.add_command(label="Send feedback", command=self._send_feedback)
    help_menu.add_command(label="Export diagnostics…", command=self._export_diagnostics)
    help_menu.add_separator()
    help_menu.add_command(label="Activate Pro license…", command=self._show_license_dialog)

    self._help_btn = ctk.CTkButton(
      search_row,
      text="Help",
      width=70,
      height=38,
      corner_radius=8,
      fg_color="#4a5568",
      hover_color="#2d3748",
      command=lambda: help_menu.tk_popup(
        self._help_btn.winfo_rootx(),
        self._help_btn.winfo_rooty() + self._help_btn.winfo_height(),
      ),
    )
    self._help_btn.grid(row=0, column=5, sticky="e", padx=(0, 0))
    ToolTip(self._help_btn, "About, updates, feedback, Pro license")

  def _build_notebook(self, main_content):
    # Container for tabs
    notebook_container = ctk.CTkFrame(main_content, fg_color="transparent")
    notebook_container.grid(row=3, column=0, sticky="nsew", padx=(12, 12), pady=(0, 12))
    notebook_container.rowconfigure(1, weight=1)
    notebook_container.columnconfigure(0, weight=1)

    # Tab selector with rounded corners
    self._tab_selector = ctk.CTkSegmentedButton(
      notebook_container,
      values=["📋 Shelf Order", "⭐ Wishlist", "📜 Log"],
      command=self._switch_tab,
      corner_radius=8,
      height=42,
      fg_color=self._colors["panel"],
      selected_color=self._colors["accent"],
      selected_hover_color=self._colors["button_hover"],
      unselected_color=self._colors["panel2"],
      unselected_hover_color=self._colors["border"],
    )
    self._tab_selector.grid(row=0, column=0, sticky="ew", padx=12, pady=(0, 0))
    self._tab_selector.set("📋 Shelf Order")

    # Container for tab content
    self._tab_content = ctk.CTkFrame(notebook_container, fg_color="transparent")
    self._tab_content.grid(row=1, column=0, sticky="nsew")
    self._tab_content.rowconfigure(0, weight=1)
    self._tab_content.columnconfigure(0, weight=1)

    # Build all tab frames
    self._build_order_tab(self._tab_content)
    self._build_wishlist_tab(self._tab_content)
    self._build_log_tab(self._tab_content)

    # Show the first tab
    self._current_tab = "📋 Shelf Order"
    self._switch_tab("📋 Shelf Order")

  def _build_order_tab(self, parent):
    OrderPanel(self).build_tab(parent)

  def _build_wishlist_tab(self, parent):
    WishlistPanel(self).build_tab(parent)


  def _on_wishlist_double_click(self, event):
    item = self.wishlist_tree.selection()
    if not item:
      return
    idx = self.wishlist_tree.index(item[0])
    if idx < 0 or idx >= len(self._wishlist_rows):
      return
    row = self._wishlist_rows[idx]
    popup, bg, fg, accent, btn_bg, btn_fg = self._create_album_popup_window(row)
    _, row_offset = self._add_album_cover_to_popup(popup, row, bg)
    details_frame, details_canvas = self._add_scrollable_details_area(popup, bg)
    self._populate_album_details(details_frame, row, fg, bg, row_offset)
    self._setup_details_scroll(details_frame, details_canvas)
    self._add_popup_buttons(popup, row, accent, btn_bg, btn_fg, bg, show_wishlist_button=True)

  def _on_wishlist_right_click(self, event):
    from core.wishlist import remove_from_wishlist
    item = self.wishlist_tree.identify_row(event.y)
    if not item:
      return
    values = self.wishlist_tree.item(item, "values")
    artist, title = values[0], values[1]
    remove_from_wishlist(artist, title)
    self.refresh_wishlist_tree()

  def _on_wishlist_click(self, event):
    """Handle single click on wishlist tree - open marketplace if clicking For Sale/Price column."""
    import webbrowser
    
    region = self.wishlist_tree.identify_region(event.x, event.y)
    if region != "cell":
      return
    
    column = self.wishlist_tree.identify_column(event.x)
    item = self.wishlist_tree.identify_row(event.y)
    if not item:
      return
    
    # Check if clicking on "For Sale" or "Lowest Price" columns (#3 or #4)
    if column not in ("#3", "#4"):
      return
    
    try:
      idx = self.wishlist_tree.index(item)
      if idx < 0 or idx >= len(self._wishlist_rows):
        return
      
      row = self._wishlist_rows[idx]
      num_for_sale = getattr(row, "num_for_sale", None)
      
      # Only open if there are copies for sale
      if num_for_sale is not None and num_for_sale > 0:
        release_id = getattr(row, "release_id", None)
        if release_id:
          # Open Discogs marketplace page for this release
          marketplace_url = f"https://www.discogs.com/sell/release/{release_id}"
          webbrowser.open(marketplace_url)
    except Exception as e:
      print(f"Error opening marketplace: {e}")

  def _check_wishlist_availability(self):
    """Check Discogs Marketplace for availability of all wishlist items."""
    if not can_check_wishlist_availability():
      messagebox.showinfo("Pro feature", upgrade_message("Wishlist availability check"))
      return
    import threading
    from core.wishlist import load_wishlist, save_wishlist, release_id_from_entry

    wishlist_data = load_wishlist()
    if not wishlist_data:
      self._wishlist_status_var.set("No items in wishlist")
      return

    cfg = self._get_cfg()
    if not self._has_valid_token(cfg):
      messagebox.showwarning(
        "Auth Required",
        "Sign in or enter your Discogs token in Settings to check marketplace availability.",
      )
      return

    total = len(wishlist_data)
    self._wishlist_check_btn.configure(state="disabled")
    self._wishlist_status_var.set("Checking availability...")
    self._log(f"Checking marketplace availability for {total} wishlist items…")

    progress = ProgressDialog(
      self.root,
      "Checking Availability",
      f"Fetching marketplace prices for {total} wishlist items…",
    )

    def check_availability():
      try:
        import core.api as api

        _, headers, session, _ = self._get_user_info(cfg)
        currency = (self.v_currency.get() or "USD").strip()
        available_count = 0
        skipped = 0

        for i, entry in enumerate(wishlist_data):
          artist = entry.get("artist", "")
          title = entry.get("title", "")
          release_id = release_id_from_entry(entry)
          if release_id and not entry.get("release_id"):
            entry["release_id"] = release_id

          progress_msg = f"[{i + 1}/{total}] {artist} - {title}"
          status_msg = f"Checking {i + 1}/{total}…"

          def update_ui(p=progress_msg, s=status_msg):
            progress.update_progress(p)
            self._wishlist_status_var.set(s)

          self.root.after(0, update_ui)

          if not release_id:
            skipped += 1
            continue

          lowest, num_for_sale, actual_currency = api.fetch_release_price(
            headers=headers,
            session=session,
            release_id=release_id,
            currency=currency,
          )
          entry["lowest_price"] = lowest
          entry["num_for_sale"] = num_for_sale
          entry["price_currency"] = actual_currency
          if num_for_sale and num_for_sale > 0:
            available_count += 1

        save_wishlist(wishlist_data)

        summary = f"✓ {available_count} of {total} available for purchase"
        if skipped:
          summary += f" ({skipped} skipped — no release ID)"

        def finish():
          self._wishlist_check_btn.configure(state="normal")
          self._wishlist_status_var.set(summary)
          self.refresh_wishlist_tree()
          self._log(f"Wishlist availability check complete: {summary}")
          progress.set_done(summary)

        self.root.after(0, finish)

      except Exception as e:
        def show_error():
          self._wishlist_check_btn.configure(state="normal")
          err = str(e)
          self._wishlist_status_var.set(f"Error: {err[:50]}")
          self._log(f"Wishlist availability check failed: {err}")
          progress.set_error(err[:200])
          self.root.after(2000, progress.close)

        self.root.after(0, show_error)

    threading.Thread(target=check_availability, daemon=True).start()

  def _build_log_tab(self, parent):
    self._log_tab = ctk.CTkFrame(parent, fg_color="transparent")
    self._log_tab.rowconfigure(0, weight=1)
    self._log_tab.columnconfigure(0, weight=1)
    log_wrap = ctk.CTkFrame(self._log_tab, fg_color="transparent")
    log_wrap.grid(row=0, column=0, sticky="nsew")
    log_wrap.rowconfigure(0, weight=1)
    log_wrap.columnconfigure(0, weight=1)
    log_scroll = ttk.Scrollbar(log_wrap, orient="vertical")
    log_scroll.grid(row=0, column=1, sticky="ns")
    import tkinter as tk
    self.log = tk.Text(
      log_wrap,
      height=18,
      width=90,
      yscrollcommand=log_scroll.set,
      font=("Cascadia Code", FONT_SM),
      background=self._colors["panel2"],
      foreground=self._colors["text"],
      insertbackground=self._colors["text"],
      relief="flat",
      bd=0,
      padx=12,
      pady=12,
    )
    self.log.grid(row=0, column=0, sticky="nsew")
    log_scroll.config(command=self.log.yview)

  def _on_album_double_click(self, event):
    """Show a popup with album details when a row is double-clicked."""
    item_id = self.order_tree.identify_row(event.y)
    row = self._get_row_from_item_id(item_id)
    if not row:
      return
    popup, bg, fg, accent, btn_bg, btn_fg = self._create_album_popup_window(row)
    _, row_offset = self._add_album_cover_to_popup(popup, row, bg)
    details_frame, details_canvas = self._add_scrollable_details_area(popup, bg)
    self._populate_album_details(details_frame, row, fg, bg, row_offset)
    self._setup_details_scroll(details_frame, details_canvas)
    self._add_popup_buttons(popup, row, accent, btn_bg, btn_fg, bg)

  def _get_row_from_item_id(self, item_id):
    if not item_id:
      return None
    try:
      idx = self.order_tree.index(item_id)
      if idx < 0 or idx >= len(self._tree_rows):
        return None
      return self._tree_rows[idx]
    except Exception:
      return None

  def _get_release_page_url(self, row) -> str:
    release_id = getattr(row, "release_id", None)
    url = getattr(row, "discogs_url", "") or getattr(row, "url", "")
    if url.startswith("http"):
      if "discogs.com/release/" in url:
        return url.split("?")[0]
      if release_id and "api.discogs.com/releases/" in url:
        return f"https://www.discogs.com/release/{release_id}"
    if release_id:
      return f"https://www.discogs.com/release/{release_id}"
    return ""

  def _format_marketplace_summary(self, row) -> str:
    if not getattr(row, "release_id", None):
      return ""
    lowest = getattr(row, "lowest_price", None)
    num_for_sale = getattr(row, "num_for_sale", None)
    currency = getattr(row, "price_currency", "") or self.v_currency.get().strip() or "USD"
    if num_for_sale is not None:
      if num_for_sale > 0 and lowest is not None:
        return f"From {lowest:.0f} {currency} · {num_for_sale} for sale"
      return "Not currently listed on the marketplace"
    if not self.v_show_prices.get():
      if can_fetch_prices():
        return 'Enable "Show prices" in settings, then refresh, to load marketplace data.'
      return "Marketplace prices are a Pro feature (Settings → Upgrade to Pro)."
    if lowest is not None and num_for_sale is not None and num_for_sale > 0:
      return f"From {lowest:.0f} {currency} · {num_for_sale} for sale"
    return "Not currently listed on the marketplace"

  def _create_album_popup_window(self, row):
    popup = tk.Toplevel(self.root)
    popup.title(f"Album Info: {row.artist_display} - {row.title}")
    popup.transient(self.root)
    popup.grab_set()
    popup.resizable(False, False)
    width, height = 640, 520
    popup.geometry(f"{width}x{height}")
    popup.update_idletasks()
    x = (popup.winfo_screenwidth() // 2) - (width // 2)
    y = (popup.winfo_screenheight() // 2) - (height // 2)
    popup.geometry(f"{width}x{height}+{x}+{y}")
    bg = self._colors["panel"] if hasattr(self, "_colors") else "#16213e"
    fg = self._colors["text"] if hasattr(self, "_colors") else "#eaeaea"
    accent = self._colors["accent"] if hasattr(self, "_colors") else "#6c63ff"
    btn_bg = self._colors["button_bg"] if hasattr(self, "_colors") else "#6c63ff"
    btn_fg = self._colors["button_fg"] if hasattr(self, "_colors") else "#ffffff"
    popup.outer = tk.Frame(popup, bg=bg, bd=2, relief="ridge")
    popup.outer.pack(fill="both", expand=True, padx=8, pady=8)
    return popup, bg, fg, accent, btn_bg, btn_fg

  def _add_album_cover_to_popup(self, popup, row, bg):
    cover_img = None
    # Get headers for downloading high-quality image
    try:
      headers = discogs_headers(self.v_token.get(), self.v_user_agent.get())
    except Exception:
      headers = {"User-Agent": "Mozilla/5.0"}
    
    # Try to load high-quality popup image for the release
    if hasattr(self, '_thumbnail_cache') and getattr(row, 'release_id', None):
      cover_url = getattr(row, 'cover_image_url', None) or getattr(row, 'thumb_url', None)
      cover_img = self._thumbnail_cache.load_popup_image(row.release_id, cover_url, headers)
      if not cover_img:
        # Fall back to preview size
        cover_img = self._thumbnail_cache.load_preview(row.release_id, cover_url, headers)
      if not cover_img:
        cover_img = self._thumbnail_cache.load_photo(row.release_id)
    # Always fall back to placeholder if no image is found
    if not cover_img and hasattr(self, '_thumbnail_cache'):
      cover_img = self._thumbnail_cache.get_placeholder()
    row_offset = 0
    # Create a horizontal frame to hold image and buttons
    top_frame = tk.Frame(popup.outer, bg=bg)
    # Center the top_frame horizontally
    top_frame.pack(pady=(12, 24))
    # Center content in top_frame using grid
    top_frame.grid_columnconfigure(0, weight=1)
    top_frame.grid_columnconfigure(1, weight=1)
    # Image in column 0, centered vertically
    if cover_img:
        img_label = tk.Label(top_frame, image=cover_img, bg=bg)
        img_label.image = cover_img
        img_label.grid(row=0, column=0, padx=(0, 24), sticky="nsew")
        row_offset = 1
    # Button frame in column 1, centered vertically
    btn_stack = tk.Frame(top_frame, bg=bg)
    btn_stack.grid(row=0, column=1, sticky="nsew")
    # Attach btn_stack to popup for use in _add_popup_buttons
    popup._btn_stack = btn_stack
    return cover_img, row_offset

  def _add_scrollable_details_area(self, popup, bg):
    details_canvas = tk.Canvas(popup.outer, bg=bg, highlightthickness=0)
    scrollbar = tk.Scrollbar(popup.outer, orient="vertical", command=details_canvas.yview)
    details_canvas.configure(yscrollcommand=scrollbar.set)
    details_canvas.pack(side="left", fill="both", expand=True, padx=(0,0), pady=0)
    scrollbar.pack(side="right", fill="y")
    details_frame = tk.Frame(details_canvas, bg=bg)
    details_canvas.create_window((0,0), window=details_frame, anchor="nw")
    return details_frame, details_canvas

  def _populate_album_details(self, details_frame, row, fg, bg, row_offset):
    details = [
      ("Artist", getattr(row, "artist_display", "")),
      ("Title", getattr(row, "title", "")),
      ("Year", getattr(row, "year", "")),
      ("Format", getattr(row, "format_str", getattr(row, "format", ""))),
      ("Label", getattr(row, "label", "")),
      ("Catalog #", getattr(row, "catno", "")),
      ("Country", getattr(row, "country", "")),
    ]
    marketplace = self._format_marketplace_summary(row)
    if marketplace:
      details.append(("Marketplace", marketplace))
    notes = getattr(row, "notes", "")
    if notes:
      details.append(("Your notes", notes))

    for i, (label, value) in enumerate(details):
      if value:
        tk.Label(
          details_frame, text=label + ":", anchor="e",
          font=(FONT_SEGOE_UI, FONT_LG, "bold"), bg=bg, fg=fg,
        ).grid(row=i + row_offset, column=0, sticky="e", padx=(0, 18), pady=10)
        tk.Label(
          details_frame, text=str(value), anchor="w",
          font=(FONT_SEGOE_UI, FONT_LG), bg=bg, fg=fg,
          wraplength=480, justify="left",
        ).grid(row=i + row_offset, column=1, sticky="w", padx=(0, 12), pady=10)

  def _setup_details_scroll(self, details_frame, details_canvas):
    details_frame.update_idletasks()
    details_canvas.config(scrollregion=details_canvas.bbox("all"))
    def _on_frame_configure(event):
      details_canvas.config(scrollregion=details_canvas.bbox("all"))
    details_frame.bind("<Configure>", _on_frame_configure)
    def _on_mousewheel(event):
      if event.delta:
        direction = -1 if event.delta > 0 else 1
        details_canvas.yview_scroll(direction, "units")
      elif hasattr(event, 'num'):
        if event.num == 4:
          details_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
          details_canvas.yview_scroll(1, "units")
      return "break"
    details_canvas.bind_all("<MouseWheel>", _on_mousewheel)
    details_canvas.bind_all("<Button-4>", _on_mousewheel)
    details_canvas.bind_all("<Button-5>", _on_mousewheel)
    def _unbind_mousewheel():
      details_canvas.unbind_all("<MouseWheel>")
      details_canvas.unbind_all("<Button-4>")
      details_canvas.unbind_all("<Button-5>")
    details_canvas.master.master.protocol("WM_DELETE_WINDOW", lambda: (details_canvas.master.master.destroy(), _unbind_mousewheel()))

  def _add_popup_buttons(self, popup, row, accent, btn_bg, btn_fg, bg, *, show_wishlist_button: bool = False):
    import webbrowser

    # Use the stacked button frame if present (from _add_album_cover_to_popup)
    btn_frame = getattr(popup, '_btn_stack', None)
    if btn_frame is None:
        btn_frame = tk.Frame(popup.outer, bg=bg)
        btn_frame.pack(fill="x", pady=(12,0))

    discogs_url = self._get_release_page_url(row)
    if discogs_url:
        tk.Button(
          btn_frame, text="Open in Discogs",
          command=lambda: webbrowser.open(discogs_url),
          font=(FONT_SEGOE_UI, FONT_MD), bg=accent, fg=btn_fg,
          activebackground=btn_bg, activeforeground=btn_fg, relief="groove",
        ).pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)

    from gui.audio_preview_panel import AudioPreviewPanel

    artist = getattr(row, "artist_display", "")
    album = getattr(row, "title", "")

    def get_discogs_headers():
      try:
        return discogs_headers(self.v_token.get(), self.v_user_agent.get())
      except Exception:
        return {"User-Agent": self.v_user_agent.get() or "VinylSorter/1.0"}

    AudioPreviewPanel(
      btn_frame,
      artist=artist,
      album=album,
      release_id=getattr(row, "release_id", None),
      get_headers=get_discogs_headers,
      bg=bg,
      fg=self._colors["text"] if hasattr(self, "_colors") else "#eaeaea",
      accent=accent,
    ).pack(side="top", fill="x")

    if show_wishlist_button:
      from core.wishlist import add_to_wishlist, remove_from_wishlist, is_in_wishlist
      discogs_url = getattr(row, "discogs_url", getattr(row, "url", None))
      year = getattr(row, "year", None)
      thumb_url = getattr(row, "thumb_url", None)
      cover_image_url = getattr(row, "cover_image_url", None)
      release_id = getattr(row, "release_id", None)
      wishlist_state = tk.StringVar()

      def update_wishlist_state():
        if is_in_wishlist(artist, album):
          wishlist_state.set("Remove from Wishlist")
        else:
          wishlist_state.set("Add to Wishlist")

      def toggle_wishlist():
        if is_in_wishlist(artist, album):
          remove_from_wishlist(artist, album)
        else:
          add_to_wishlist(
            artist, album, discogs_url,
            year=year,
            thumb=thumb_url,
            cover_image_url=cover_image_url,
            release_id=release_id,
          )
        update_wishlist_state()
        if hasattr(self, 'refresh_wishlist_tree'):
          self.refresh_wishlist_tree()

      update_wishlist_state()
      tk.Button(
        btn_frame, textvariable=wishlist_state, command=toggle_wishlist,
        font=(FONT_SEGOE_UI, FONT_MD), bg="#ffb347", fg="#222",
        activebackground="#ffd580", activeforeground="#222", relief="groove",
      ).pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)

    tk.Button(btn_frame, text="Close", command=popup.destroy, font=(FONT_SEGOE_UI, FONT_MD), bg=btn_bg, fg=btn_fg, activebackground=accent, activeforeground=btn_fg, relief="groove").pack(side="top", fill="x", padx=12, pady=(0, 0), ipadx=12, ipady=4)

  def _choose_dir(self) -> None:
    directory = filedialog.askdirectory(initialdir=self.v_output_dir.get() or str(Path.cwd()))
    if directory:
      self.v_output_dir.set(directory)

  def _setup_tooltips(self) -> None:
    """Set up tooltips for all interactive widgets."""
    ToolTip(self._output_entry, "Directory where sorted lists will be saved (TXT, CSV, JSON)")
    ToolTip(self._browse_btn, "Browse for an output folder")
    ToolTip(self._poll_spin, "How often to check for collection changes (seconds)")
    ToolTip(self._json_check, "Also save output as JSON file")
    ToolTip(self._prices_check, "Fetch marketplace prices. Cached locally for 7 days.\nEnable this, then click Refresh to load prices.")
    ToolTip(self._currency_combo, "Currency for price display")
    ToolTip(self._sort_combo, "How to sort your collection:\n• artist: A-Z by artist name\n• title: A-Z by album title\n• year: Chronological\n• price_asc/desc: By price")
    
    # Theme button
    ToolTip(self.theme_btn, "Switch between dark and light mode")
    
    # Search
    ToolTip(self._search_entry, "Filter your collection - type to search artist, title, or label (Ctrl+F)")
    ToolTip(self._clear_btn, "Clear the search filter (Esc)")
    
    # Action buttons
    ToolTip(self._refresh_btn, "Fetch your collection from Discogs and rebuild the shelf order (F5)")
    ToolTip(self._export_btn, "Save the current shelf order to files in the output directory (Ctrl+S)")
    ToolTip(self._print_btn, "Print the current shelf order (Ctrl+P)")
    ToolTip(self._stop_btn, "Stop the auto-refresh timer and exit (Ctrl+Q)")
    ToolTip(self._refresh_prices_btn, "Clear cached prices and fetch fresh data from Discogs Marketplace")
    
    # Manual order controls
    ToolTip(self._manual_order_check, "Enable manual ordering mode.\nDrag rows to reorder your collection.")
    ToolTip(self._reset_order_btn, "Clear custom order and revert to automatic sorting")
    ToolTip(self._move_up_btn, "Move selected item up one position (Alt+Up)")
    ToolTip(self._move_down_btn, "Move selected item down one position (Alt+Down)")

  def _apply_startup_window_state(self) -> None:
    self._maximize_window()
    self._update_maximize_button()

  def _setup_keyboard_shortcuts(self) -> None:
    """Set up keyboard shortcuts for common actions."""
    # Ctrl+F - Focus search
    self.root.bind("<Control-f>", lambda e: self._focus_search())
    self.root.bind("<Control-F>", lambda e: self._focus_search())
    
    # Escape - Clear search (when search has focus)
    self._search_entry.bind("<Escape>", lambda e: self._clear_search())
    
    # F11 - Toggle maximize / restore
    self.root.bind("<F11>", lambda e: self._toggle_window_maximize())

    # F5 - Refresh
    self.root.bind("<F5>", lambda e: self._refresh_now())
    
    # Ctrl+R - Refresh (alternative)
    self.root.bind("<Control-r>", lambda e: self._refresh_now())
    self.root.bind("<Control-R>", lambda e: self._refresh_now())
    
    # Ctrl+S - Export/Save
    self.root.bind("<Control-s>", lambda e: self._export_files())
    self.root.bind("<Control-S>", lambda e: self._export_files())
    
    # Ctrl+P - Print
    self.root.bind("<Control-p>", lambda e: self._print_current())
    self.root.bind("<Control-P>", lambda e: self._print_current())
    
    # Ctrl+Q - Quit
    self.root.bind("<Control-q>", lambda e: self._stop_app())
    self.root.bind("<Control-Q>", lambda e: self._stop_app())
    
    # Ctrl+D - Toggle dark/light mode
    self.root.bind("<Control-d>", lambda e: self._toggle_theme())
    self.root.bind("<Control-D>", lambda e: self._toggle_theme())
    
    # Alt+Up/Down - Move items in manual order mode
    self.root.bind("<Alt-Up>", lambda e: self._move_item_up())
    self.root.bind("<Alt-Down>", lambda e: self._move_item_down())
  
  def _focus_search(self) -> None:
    """Focus the search entry field."""
    self._search_entry.focus_set()
    self._search_entry.select_range(0, "end")
  
  def _clear_search(self) -> None:
    """Clear the search field."""
    self.v_search.set("")
    self._search_entry.focus_set()

  # ─────────────────────────────────────────────────────────────────────────────
  # Drag-and-Drop Methods for Manual Reordering
  # ─────────────────────────────────────────────────────────────────────────────
  
  def _toggle_manual_order(self) -> None:
    """Toggle manual ordering mode on/off."""
    if self.v_manual_order_enabled.get() and not can_use_manual_order():
      self.v_manual_order_enabled.set(False)
      messagebox.showinfo("Pro feature", upgrade_message("Manual shelf order"))
      return
    enabled = self.v_manual_order_enabled.get()
    self._manual_order.set_enabled(enabled)
    if enabled:
      self._log("Manual order mode enabled. Drag rows to reorder.")
      # Save current order as the starting point
      if self._tree_rows:
        release_ids = [r.release_id for r in self._tree_rows if r.release_id]
        self._manual_order.set_order(release_ids)
    else:
      self._log("Manual order mode disabled. Using automatic sort.")
    # Re-render to show current state
    if self._last_result:
      self._render_order(self._last_result)
  
  def _reset_manual_order(self) -> None:
    """Reset to automatic sorting, clearing any manual order."""
    if not messagebox.askyesno("Reset Order", "Reset to automatic sorting?\n\nThis will clear your custom order."):
      return
    self._manual_order.clear()
    self.v_manual_order_enabled.set(False)
    self._log("Manual order cleared. Reverted to automatic sort.")
    # Trigger a re-render with automatic sort
    if self._last_result:
      self._render_order(self._last_result)
  
  def _on_tree_motion(self, event) -> None:
    """Handle mouse motion over the treeview for album artwork preview."""
    if not self._thumbnails_enabled or not self._image_preview:
      return

    def hide_preview():
      if self._image_preview and self._hover_release_id is not None:
        self._image_preview.hide(delay=50)
        self._hover_release_id = None

    region = self.order_tree.identify_region(event.x, event.y)
    column = self.order_tree.identify_column(event.x)

    # Only show preview when hovering the image column (#0 or tree region)
    if column != "#0" and region != "tree":
      hide_preview()
      return

    item = self.order_tree.identify_row(event.y)
    if not item:
      hide_preview()
      return

    try:
      idx = self.order_tree.index(item)
      if idx < 0 or idx >= len(self._tree_rows):
        return

      row = self._tree_rows[idx]
      if not row.release_id or row.release_id == self._hover_release_id:
        return

      self._hover_release_id = row.release_id

      try:
        headers = discogs_headers(self.v_token.get(), self.v_user_agent.get())
      except Exception:
        headers = {"User-Agent": "Mozilla/5.0"}

      screen_x = event.x_root
      screen_y = event.y_root
      cover_url = getattr(row, 'cover_image_url', '') or row.thumb_url
      self._image_preview.show(row.release_id, cover_url, headers, screen_x, screen_y)
    except Exception as e:
      print(f"Hover error: {e}")
  
  def _on_tree_leave(self, event) -> None:
    """Handle mouse leaving the treeview."""
    if self._image_preview:
      self._image_preview.hide()
    self._hover_release_id = None

  def _on_drag_start(self, event) -> None:
    """Handle mouse button press to start drag operation."""
    if not self.v_manual_order_enabled.get():
      return  # Drag only works in manual order mode
    
    # Identify the item under cursor
    item = self.order_tree.identify_row(event.y)
    if not item:
      return
    
    # Store the starting position
    self._drag_item_id = item
    try:
      self._drag_start_index = self.order_tree.index(item)
    except Exception:
      self._drag_start_index = None
    
    # Select the item and add visual feedback
    self.order_tree.selection_set(item)
    self.order_tree.item(item, tags=("dragging",))
  
  def _on_drag_motion(self, event) -> None:
    """Handle mouse motion during drag."""
    if not self.v_manual_order_enabled.get():
      return
    if self._drag_item_id is None:
      return
    
    # Find the item at current position
    target_item = self.order_tree.identify_row(event.y)
    if not target_item or target_item == self._drag_item_id:
      return
    
    try:
      # Get current positions
      drag_index = self.order_tree.index(self._drag_item_id)
      target_index = self.order_tree.index(target_item)
      
      # Move the item
      self.order_tree.move(self._drag_item_id, "", target_index)
      
      # Update internal row list
      if 0 <= drag_index < len(self._tree_rows) and 0 <= target_index < len(self._tree_rows):
        row = self._tree_rows.pop(drag_index)
        self._tree_rows.insert(target_index, row)
        
        # Update row numbers in treeview
        self._update_row_numbers()
    except Exception:
      pass
  
  def _on_drag_end(self, event) -> None:
    """Handle mouse button release to end drag operation."""
    if self._drag_item_id:
      # Remove dragging visual
      try:
        # Restore normal tag based on new position
        index = self.order_tree.index(self._drag_item_id)
        tag = "row_odd" if index % 2 == 1 else "row_even"
        self.order_tree.item(self._drag_item_id, tags=(tag,))
      except Exception:
        pass
    
    # Save the new order if manual mode is enabled
    if self.v_manual_order_enabled.get() and self._tree_rows:
      release_ids = [r.release_id for r in self._tree_rows if r.release_id]
      self._manual_order.set_order(release_ids)
      self._log(f"Order saved. {len(release_ids)} items.")
    
    # Reset drag state
    self._drag_item_id = None
    self._drag_start_index = None
    
    # Update all row tags for alternating colors
    self._update_row_tags()
  
  def _update_row_numbers(self) -> None:
    """Update the row numbers in the treeview after reordering."""
    for i, item in enumerate(self.order_tree.get_children()):
      values = list(self.order_tree.item(item, "values"))
      if values:
        values[0] = str(i + 1)  # Update row number
        self.order_tree.item(item, values=values)
  
  def _update_row_tags(self) -> None:
    """Update row tags for alternating colors."""
    for i, item in enumerate(self.order_tree.get_children()):
      tag = "row_odd" if i % 2 == 1 else "row_even"
      self.order_tree.item(item, tags=(tag,))
  
  def _move_item_up(self) -> None:
    """Move selected item up one position."""
    if not self.v_manual_order_enabled.get():
      messagebox.showinfo("Manual Order", "Enable 'Manual Order Mode' first to reorder items.")
      return
    
    selection = self.order_tree.selection()
    if not selection:
      return
    
    item = selection[0]
    try:
      index = self.order_tree.index(item)
      if index > 0:
        # Move in treeview
        self.order_tree.move(item, "", index - 1)
        # Move in internal list
        row = self._tree_rows.pop(index)
        self._tree_rows.insert(index - 1, row)
        # Update display and save
        self._update_row_numbers()
        self._update_row_tags()
        self._save_current_order()
    except Exception:
      pass
  
  def _move_item_down(self) -> None:
    """Move selected item down one position."""
    if not self.v_manual_order_enabled.get():
      messagebox.showinfo("Manual Order", "Enable 'Manual Order Mode' first to reorder items.")
      return
    
    selection = self.order_tree.selection()
    if not selection:
      return
    
    item = selection[0]
    try:
      index = self.order_tree.index(item)
      children = self.order_tree.get_children()
      if index < len(children) - 1:
        # Move in treeview
        self.order_tree.move(item, "", index + 1)
        # Move in internal list
        row = self._tree_rows.pop(index)
        self._tree_rows.insert(index + 1, row)
        # Update display and save
        self._update_row_numbers()
        self._update_row_tags()
        self._save_current_order()
    except Exception:
      pass
  
  def _save_current_order(self) -> None:
    """Save the current order to the manual order manager."""
    if self._tree_rows:
      release_ids = [r.release_id for r in self._tree_rows if r.release_id]
      self._manual_order.set_order(release_ids)
      self._log(f"Order saved. {len(release_ids)} items.")

  # ─────────────────────────────────────────────────────────────────────────────

  def _refresh_prices(self) -> None:
    """Clear cached prices and trigger a refresh with price fetching enabled."""
    if not can_fetch_prices():
      messagebox.showinfo("Pro feature", upgrade_message("Marketplace prices"))
      return
    currency = self.v_currency.get().strip() or "USD"
    cleared = self._collection_cache.clear_prices(currency)
    self._log(f"Cleared {cleared} cached prices for {currency}.")
    
    # Enable show prices and trigger refresh
    self.v_show_prices.set(True)
    self._refresh_now()

  def _on_show_prices_change(self) -> None:
    if self.v_show_prices.get() and not can_fetch_prices():
      self.v_show_prices.set(False)
      messagebox.showinfo("Pro feature", upgrade_message("Marketplace prices"))
      return
    self._save_settings()

  def _save_settings(self) -> None:
    """Save current settings to config file."""
    try:
      config = {
        "token": self.v_token.get().strip(),
        "user_agent": self.v_user_agent.get().strip(),
        "output_dir": self.v_output_dir.get().strip(),
        "per_page": self.v_per_page.get(),
        "write_json": self.v_json.get(),
        "poll_seconds": self.v_poll.get(),
        "show_prices": self.v_show_prices.get(),
        "currency": self.v_currency.get().strip(),
        "sort_by": self.v_sort_by.get().strip(),
        "formats": self._selected_formats(),
        "divider_mode": self._divider_mode_value(),
      }
      if getattr(self, "_oauth_access_token", None):
        config["oauth_access_token"] = self._oauth_access_token
      if getattr(self, "_oauth_access_secret", None):
        config["oauth_access_secret"] = self._oauth_access_secret
      save_config(config)
      self._refresh_worker_cfg()
    except Exception:
      pass

  def _open_output_dir(self) -> None:
    path = self.v_output_dir.get().strip() or str(Path.cwd())
    try:
      import platform
      if platform.system() == "Windows":
        os.startfile(path)
      elif platform.system() == "Darwin":
        subprocess.run(["open", path], check=False)
      else:
        subprocess.run(["xdg-open", path], check=False)
    except Exception:
      pass

  def _update_auth_buttons_state(self) -> None:
    """Enable/disable Sign in and Sign out based on OAuth state."""
    if not hasattr(self, "_signin_btn") or not hasattr(self, "_signout_btn"):
      return
    signed_in = bool((self._oauth_access_token or "").strip())
    self._signin_btn.configure(state="disabled" if signed_in else "normal")
    self._signout_btn.configure(state="normal" if signed_in else "disabled")
    if hasattr(self, "_auth_status_label"):
      self._auth_status_label.configure(
        text="Signed in to Discogs" if signed_in else "Not signed in",
        text_color=self._colors["success"] if signed_in else self._colors["muted"],
      )

  def _divider_mode_value(self) -> str:
    mode = DIVIDER_MODE_BY_LABEL.get(self.v_divider_mode.get(), "none")
    if mode != "none" and not can_use_abc_dividers():
      return "none"
    return mode

  def _show_about_dialog(self) -> None:
    from gui.about_dialog import AboutDialog
    AboutDialog(self.root)

  def _show_license_dialog(self) -> None:
    from gui.license_dialog import LicenseDialog
    LicenseDialog(self.root, on_changed=self._update_pro_ui)

  def _check_for_updates(self) -> None:
    from core.update_checker import check_for_update
    from core.version import PURCHASE_URL
    import webbrowser

    info = check_for_update()
    if not info:
      messagebox.showinfo("Updates", "You are on the latest version.")
      return
    msg = f"Version {info.latest_version} is available."
    if info.release_notes:
      msg += f"\n\n{info.release_notes}"
    if info.download_url:
      msg += f"\n\nDownload: {info.download_url}"
    if messagebox.askyesno("Update available", msg + "\n\nOpen download page?"):
      webbrowser.open(info.download_url or PURCHASE_URL)

  def _send_feedback(self) -> None:
    import webbrowser
    from core.version import FEEDBACK_MAILTO
    webbrowser.open(FEEDBACK_MAILTO)

  def _export_diagnostics(self) -> None:
    from core.diagnostics import export_diagnostics_zip
    try:
      path = export_diagnostics_zip()
      messagebox.showinfo("Diagnostics", f"Saved support bundle:\n{path}")
      self._log(f"Exported diagnostics: {path}")
    except Exception as exc:
      messagebox.showerror("Diagnostics", str(exc))

  def _update_pro_ui(self) -> None:
    """Refresh Pro-gated controls and upgrade banner."""
    pro = is_pro()
    if hasattr(self, "_license_status_label"):
      self._license_status_label.configure(text=license_summary())
    if hasattr(self, "_pro_banner"):
      if pro:
        self._pro_banner.grid_remove()
        self._record_limit_truncated = False
      elif getattr(self, "_record_limit_truncated", False):
        self._pro_banner_label.configure(
          text=f"Free tier shows {FREE_RECORD_LIMIT} records. Upgrade to Pro for your full collection, prices, and more.",
        )
        self._pro_banner.grid()
      else:
        self._pro_banner.grid_remove()
    if hasattr(self, "_prices_check") and not can_fetch_prices():
      self.v_show_prices.set(False)
      self._prices_check.configure(state="disabled")
    elif hasattr(self, "_prices_check"):
      self._prices_check.configure(state="normal")
    if hasattr(self, "_manual_order_check"):
      state = "normal" if can_use_manual_order() else "disabled"
      self._manual_order_check.configure(state=state)
      if not can_use_manual_order() and self.v_manual_order_enabled.get():
        self.v_manual_order_enabled.set(False)
        self._manual_order.set_enabled(False)
    if hasattr(self, "_wishlist_check_btn"):
      self._wishlist_check_btn.configure(state="normal" if can_check_wishlist_availability() else "disabled")
    if hasattr(self, "_divider_mode_combo") and not can_use_abc_dividers():
      if self._divider_mode_value() != "none":
        self.v_divider_mode.set(DIVIDER_MODE_LABELS["none"])

  def _ensure_oauth_configured(self) -> tuple[str, str] | None:
    """Return consumer credentials from the bundled production build."""
    from core.oauth_discogs import _get_consumer_credentials

    creds = _get_consumer_credentials(None)
    if creds:
      return creds
    messagebox.showerror(
      "Sign-in unavailable",
      "This build is missing Discogs OAuth credentials.\n\n"
      "Install the official release, or contact support if you downloaded from the project site.",
    )
    return None

  def _do_oauth_signin(self) -> None:
    """Run OAuth flow and save tokens. Uses bundled app credentials."""
    from core.oauth_discogs import run_oauth_flow

    creds = self._ensure_oauth_configured()
    if not creds:
      return
    try:
      self._log("Opening browser for Discogs sign-in…")
      access_token, access_secret = run_oauth_flow(
        creds[0], creds[1],
        self.v_user_agent.get().strip() or "VinylSorter/1.0",
      )
      self._oauth_access_token = access_token
      self._oauth_access_secret = access_secret
      self._save_settings()
      self._update_auth_buttons_state()
      self._log("Signed in successfully. Refresh to load your collection.")
      messagebox.showinfo("Signed in", "Sign-in complete. Refreshing your collection…")
      self._refresh_now()
    except Exception as e:
      self._log(f"OAuth failed: {e}")
      messagebox.showerror("Sign-in Failed", str(e))

  def _do_oauth_signout(self) -> None:
    """Clear OAuth tokens, clear all records from view, and fall back to token."""
    self._oauth_access_token = ""
    self._oauth_access_secret = ""
    self._save_settings()
    self._update_auth_buttons_state()

    # Clear collection cache so next refresh fetches fresh (or requires re-auth)
    self._collection_cache.clear()

    # Clear manual order state
    self._manual_order.clear()
    if hasattr(self, "v_manual_order_enabled"):
      self.v_manual_order_enabled.set(False)

    # Clear the shelf order view
    self._last_result = None
    self._tree_rows = []
    if hasattr(self, "order_tree"):
      self._clear_treeview()
    if hasattr(self, "_order_empty_label"):
      self._show_order_empty_state(True)
    if hasattr(self, "_order_loading_label"):
      self._show_order_loading_state(False)
    if hasattr(self, "v_match"):
      self.v_match.set("0 items")

    self._log("Signed out. Records cleared. Sign in again to reload your collection.")
    messagebox.showinfo("Signed out", "Signed out and cleared the collection view. Click Sign in with Discogs to reconnect.")

  def _switch_tab(self, tab_name: str) -> None:
    """Switch between tabs in the custom tab system."""
    # Hide all tabs
    self._order_tab.grid_forget()
    self._wishlist_tab.grid_forget()
    self._log_tab.grid_forget()

    # Show the selected tab
    if tab_name == "📋 Shelf Order":
      self._order_tab.grid(row=0, column=0, sticky="nsew")
    elif tab_name == "⭐ Wishlist":
      self._wishlist_tab.grid(row=0, column=0, sticky="nsew")
    elif tab_name == "📜 Log":
      self._log_tab.grid(row=0, column=0, sticky="nsew")

    self._current_tab = tab_name

  def _toggle_settings_sidebar(self) -> None:
    """Collapse or expand the settings sidebar."""
    self._settings_collapsed = not self._settings_collapsed
    frm = self._settings_frame.master
    row = getattr(self, "_settings_row", 1)
    if self._settings_collapsed:
      self._settings_frame.grid_remove()
      self._settings_expand_tab.grid(row=row, column=0, sticky="ns", padx=(20, 10), pady=(16, 12))
      self._settings_collapse_btn.configure(text="▶")
    else:
      self._settings_expand_tab.grid_remove()
      self._settings_frame.grid(row=row, column=0, sticky="nsew", padx=(20, 10), pady=(16, 12))
      self._settings_collapse_btn.configure(text="◀")

  def _toggle_theme(self) -> None:
    """Toggle between dark and light mode."""
    self.v_dark_mode.set(not self.v_dark_mode.get())
    self._apply_theme()

  def _apply_theme(self) -> None:
    """Apply the current theme colors to all widgets."""
    self._set_theme_colors()
    self._configure_styles()
    self._update_theme_button()
    self._update_header()
    self._update_ctk_frames()
    self._update_tab_selector()
    self._update_toolbar_widgets()
    self._update_status_bar_widgets()
    self._update_treeview_widget()
    self._update_settings_entries()
    self._update_settings_frames()
    self._update_log_widget()
    self._update_root_bg()

  def _set_theme_colors(self):
    if self.v_dark_mode.get():
      self._colors = self._dark_colors.copy()
      self.theme_btn.configure(text="☀️ Light")  # Label = target mode (click to switch to light)
      ctk.set_appearance_mode("dark")
    else:
      self._colors = self._light_colors.copy()
      self.theme_btn.configure(text="🌙 Dark")  # Label = target mode (click to switch to dark)
      ctk.set_appearance_mode("light")

  def _update_theme_button(self):
    # Update CustomTkinter button - label shows target mode (what you switch to)
    try:
      if self.v_dark_mode.get():
        self.theme_btn.configure(text="☀️ Light", fg_color=self._colors["accent"], hover_color=self._colors["button_hover"])
        ctk.set_appearance_mode("dark")
      else:
        self.theme_btn.configure(text="🌙 Dark", fg_color=self._colors["accent"], hover_color=self._colors["button_hover"])
        ctk.set_appearance_mode("light")
    except Exception:
      pass

  def _update_header(self):
    # Update CustomTkinter header widgets
    try:
      self._header_title.configure(text_color=self._colors["text"])
      self._header_subtitle.configure(text_color=self._colors["muted"])
    except Exception:
      pass

  def _update_ctk_frames(self):
    """Update CustomTkinter frame colors for theme"""
    try:
      # Update Settings panel
      if hasattr(self, '_settings_frame'):
        self._settings_frame.configure(
          fg_color=self._colors["panel"],
          border_color=self._colors.get("card_border", self._colors["border"])
        )
      if hasattr(self, '_settings_expand_tab'):
        self._settings_expand_tab.configure(
          fg_color=self._colors["panel"],
          border_color=self._colors.get("card_border", self._colors["border"])
        )
      # Update order table wrapper if it exists
      if hasattr(self, 'order_tree'):
        parent = self.order_tree.master
        if hasattr(parent, 'configure'):
          try:
            parent.configure(
              fg_color=self._colors["panel"],
              border_color=self._colors.get("card_border", self._colors["border"])
            )
          except:
            pass
      # Update wishlist table wrapper if it exists
      if hasattr(self, 'wishlist_tree'):
        parent = self.wishlist_tree.master
        if hasattr(parent, 'configure'):
          try:
            parent.configure(
              fg_color=self._colors["panel"],
              border_color=self._colors.get("card_border", self._colors["border"])
            )
          except:
            pass
    except Exception:
      pass

  def _update_tab_selector(self):
    """Update tab selector colors for theme"""
    try:
      if hasattr(self, '_tab_selector'):
        self._tab_selector.configure(
          fg_color=self._colors["panel"],
          selected_color=self._colors["accent"],
          selected_hover_color=self._colors["button_hover"],
          unselected_color=self._colors["panel2"],
          unselected_hover_color=self._colors["border"],
        )
    except Exception:
      pass

  def _update_toolbar_widgets(self):
    """Update toolbar widgets colors for theme"""
    try:
      # Order toolbar widgets
      if hasattr(self, '_manual_order_check'):
        self._manual_order_check.configure(
          fg_color=self._colors["accent"],
          hover_color=self._colors["button_hover"],
        )
      if hasattr(self, '_manual_order_hint'):
        self._manual_order_hint.configure(text_color=self._colors["muted"])
      if hasattr(self, '_reset_order_btn'):
        self._reset_order_btn.configure(
          fg_color="#f59e0b" if self.v_dark_mode.get() else "#f59e0b",
          hover_color="#d97706"
        )
      if hasattr(self, '_move_up_btn'):
        self._move_up_btn.configure(
          fg_color="#4a5568" if self.v_dark_mode.get() else "#64748b",
          hover_color="#2d3748" if self.v_dark_mode.get() else "#475569"
        )
      if hasattr(self, '_move_down_btn'):
        self._move_down_btn.configure(
          fg_color="#4a5568" if self.v_dark_mode.get() else "#64748b",
          hover_color="#2d3748" if self.v_dark_mode.get() else "#475569"
        )
      # Wishlist toolbar widgets
      if hasattr(self, '_wishlist_check_btn'):
        self._wishlist_check_btn.configure(
          fg_color=self._colors["accent"],
          hover_color=self._colors["button_hover"],
        )
    except Exception:
      pass

  def _update_status_bar_widgets(self):
    try:
      if not hasattr(self, "_status_bar"):
        return
      self._status_bar.configure(fg_color=self._colors["accent"])
      self._status_label.configure(fg_color="transparent", text_color="#ffffff")
      for widget in [self._count_icon, self._count_label, self._sync_icon, self._sync_label,
                     self._value_sep, self._value_icon, self._value_label]:
        try:
          widget.configure(fg_color="transparent", text_color="#ffffff")
        except Exception:
          pass
    except Exception:
      pass

  def _update_treeview_widget(self):
    try:
      self._configure_treeview_style()
      if hasattr(self, "_order_empty_label"):
        self._order_empty_label.configure(text_color=self._colors["muted"])
      if hasattr(self, "_order_loading_label"):
        self._order_loading_label.configure(text_color=self._colors["muted"])
      if hasattr(self, "_order_loading_detail"):
        self._order_loading_detail.configure(text_color=self._colors["muted"])
      if hasattr(self, "_order_loading_progress"):
        self._order_loading_progress.configure(
          progress_color=self._colors["accent"],
          fg_color=self._colors.get("panel2", self._colors["border"]),
        )
      if hasattr(self, "_order_loading_spinner"):
        self._order_loading_spinner.set_colors(
          bg=self._colors["panel"],
          accent=self._colors["accent"],
        )
      if hasattr(self, "_order_loading_overlay"):
        self._order_loading_overlay.configure(fg_color=self._colors["panel"])
      if hasattr(self, "_wishlist_empty_label"):
        self._wishlist_empty_label.configure(text_color=self._colors["muted"])
      if self.v_dark_mode.get():
        self.order_tree.tag_configure("search_match", background="#fbbf24", foreground="#1a1a2e")
        self.order_tree.tag_configure("row_even", background=self._colors["order_bg"], foreground=self._colors["order_fg"])
        self.order_tree.tag_configure("row_odd", background="#1a2d4d", foreground=self._colors["order_fg"])
        self.order_tree.tag_configure("dragging", background=self._colors["accent"], foreground="#ffffff")
      else:
        self.order_tree.tag_configure("search_match", background="#fef08a", foreground="#1a1a2e")
        self.order_tree.tag_configure("row_even", background=self._colors["order_bg"], foreground=self._colors["order_fg"])
        self.order_tree.tag_configure("row_odd", background="#e8eef4", foreground=self._colors["order_fg"])
        self.order_tree.tag_configure("dragging", background=self._colors["accent"], foreground="#ffffff")
      if self._last_result:
        self._render_order(self._last_result)
    except Exception:
      pass

  def _update_settings_entries(self):
    try:
      entry_config = {
        "bg": self._colors["order_bg"],
        "fg": self._colors["order_fg"],
        "insertbackground": self._colors["order_fg"],
        "highlightbackground": self._colors["border"],
        "highlightcolor": self._colors["accent"],
      }
      if getattr(self, "_output_entry", None) is not None:
        try:
          self._output_entry.config(**entry_config)
        except Exception:
          pass
      self._poll_spin.config(
        bg=self._colors["order_bg"],
        fg=self._colors["order_fg"],
        buttonbackground=self._colors["border"],
        insertbackground=self._colors["order_fg"],
        highlightbackground=self._colors["border"],
        highlightcolor=self._colors["accent"],
      )
      menu_config = {
        "bg": self._colors["order_bg"],
        "fg": self._colors["order_fg"],
        "activebackground": self._colors["accent"],
        "activeforeground": "#ffffff",
      }
      for widget in [self._currency_combo, self._sort_combo]:
        try:
          widget.config(**menu_config)
          widget["menu"].config(**menu_config)
        except Exception:
          pass
    except Exception:
      pass

  def _update_settings_frames(self):
    if getattr(self, "_settings", None) is not None:
      self._settings.update_section_theme()

  def _update_log_widget(self):
    try:
      self.log.config(
        background=self._colors["order_bg"],
        foreground=self._colors["order_fg"],
        insertbackground=self._colors["order_fg"],
      )
    except Exception:
      pass

  def _update_root_bg(self):
    # Update CustomTkinter root window
    try:
      self.root.configure(fg_color=self._colors["panel2"])
    except Exception:
      pass

  def _log(self, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    self.log_q.put(f"[{ts}] {msg}\n")

  def _set_status_async(self, text: str) -> None:
    """Update the status bar from a background thread."""
    try:
      self.root.after(0, lambda: self.v_status.set(text))
    except Exception:
      pass

  def _report_build_progress(
    self,
    action: str,
    message: str | None = None,
    fraction: float | None = None,
  ) -> None:
    """Thread-safe progress for the loading overlay (processed on the main thread)."""
    self.progress_q.put((action, message, fraction))

  def _pump_queues(self) -> None:
    self._handle_log_queue()
    self._handle_result_queue()
    self._handle_progress_queue()
    self.root.after(100, self._pump_queues)

  def _handle_log_queue(self) -> None:
    try:
      while True:
        line = self.log_q.get_nowait()
        self.log.insert("end", line)
        self.log.see("end")
    except queue.Empty:
      pass

  def _handle_result_queue(self) -> None:
    try:
      while True:
        result = self.result_q.get_nowait()
        self._last_result = result
        self._render_order(result)
        self._update_status_bar(result)
    except queue.Empty:
      pass

  def _handle_progress_queue(self) -> None:
    try:
      while True:
        item = self.progress_q.get_nowait()
        action = item[0]
        message = item[1] if len(item) > 1 else None
        fraction = item[2] if len(item) > 2 else None
        self._process_progress_action(action, message, fraction)
    except queue.Empty:
      pass

  def _is_loading_overlay_visible(self) -> bool:
    overlay = getattr(self, "_order_loading_overlay", None)
    if overlay is None:
      return False
    try:
      return bool(overlay.winfo_ismapped())
    except Exception:
      return False

  def _update_loading_progress(self, message: str, fraction: float | None = None, *, error: bool = False) -> None:
    self._loading_base_message = message
    self._loading_last_fraction = fraction
    if hasattr(self, "_order_loading_detail"):
      display = message
      if fraction is not None and not error:
        display = f"{message} ({int(fraction * 100)}%)"
      self._order_loading_detail.configure(
        text=display,
        text_color=self._colors["accent3"] if error else self._colors["muted"],
      )
    if hasattr(self, "_order_loading_label") and error:
      self._order_loading_label.configure(text="Could not load collection")
    bar = getattr(self, "_order_loading_progress", None)
    if bar is None:
      return
    try:
      if error:
        bar.stop()
        bar.set(0)
      elif fraction is not None:
        bar.stop()
        bar.set(max(0.0, min(float(fraction), 1.0)))
      else:
        bar.set(0)
        bar.start()
    except Exception:
      pass

  def _process_progress_action(self, action: str, message: str | None, fraction: float | None = None) -> None:
    if action == "show":
      self._set_action_buttons_state("disabled")
      if self._progress_dialog is None:
        self._progress_dialog = ProgressDialog(self.root, "Working...", message or "Please wait...")
      if self._is_loading_overlay_visible():
        self._update_loading_progress(message or "Working…", fraction)
    elif action == "update":
      if self._last_result is None and not self._is_loading_overlay_visible():
        self._show_order_loading_state(True)
      if self._progress_dialog is not None:
        self._progress_dialog.update_progress(message or "")
      if self._is_loading_overlay_visible():
        self._update_loading_progress(message or "Loading…", fraction)
    elif action == "message" and self._progress_dialog is not None:
      self._progress_dialog.update_message(message or "")
    elif action == "error":
      if self._is_loading_overlay_visible():
        self._update_loading_progress(message or "An error occurred.", None, error=True)
      if self._progress_dialog is not None:
        self._progress_dialog.set_error(message or "An error occurred.")
        self._progress_dialog.top.after(1600, self._progress_dialog.close)
        self._progress_dialog = None
      self._set_action_buttons_state("normal")
    elif action == "done":
      if self._is_loading_overlay_visible():
        self._update_loading_progress(message or "Done!", 1.0)
      if self._progress_dialog is not None:
        self._progress_dialog.set_done(message or self._progress_dialog.DONE_MESSAGE)
        self._progress_dialog = None
      self._set_action_buttons_state("normal")
    elif action == "close" and self._progress_dialog is not None:
      self._progress_dialog.close()
      self._progress_dialog = None
      self._set_action_buttons_state("normal")

  def _render_order(self, result: BuildResult) -> None:
    """Render the shelf order in the Treeview widget."""
    self._show_order_loading_state(False)  # First build arrived
    self._clear_treeview()
    if not result.rows_sorted:
      self._tree_rows = []
      self.v_match.set("0 items")
      self._show_order_empty_state(True)
      return

    rows = self._apply_manual_order_if_enabled(result)
    rows = self._filter_rows_by_format(rows)
    if not rows:
      self._tree_rows = []
      self.v_match.set("0 items")
      self._show_order_empty_state(True)
      return
    self._show_order_empty_state(False)
    display_rows, truncated = apply_record_limit(list(rows))
    self._record_limit_truncated = truncated
    self._tree_rows = display_rows
    self._update_pro_ui()
    self._show_or_hide_price_column()
    placeholder = self._get_placeholder_image()
    self._populate_treeview_rows(display_rows, placeholder)
    total = len(rows)
    if truncated:
      self.v_match.set(f"{len(display_rows)} of {total} items (Free limit)")
    else:
      self.v_match.set(f"{len(display_rows)} items")
    self._highlight_search()
    if self._thumbnails_enabled:
      self._download_missing_thumbnails(rows)

  def _show_order_loading_state(self, show: bool) -> None:
    """Show or hide the loading collection overlay."""
    if hasattr(self, "_order_loading_overlay"):
      if show:
        self._order_loading_overlay.grid()
        if hasattr(self, "_order_loading_spinner"):
          self._order_loading_spinner.start()
        self._loading_started_at = time.time()
        self._start_loading_elapsed_timer()
        self._update_loading_progress("Connecting to Discogs…", 0.0)
        if hasattr(self, "_order_loading_label"):
          self._order_loading_label.configure(text="Loading your collection…")
      else:
        self._stop_loading_elapsed_timer()
        if hasattr(self, "_order_loading_spinner"):
          self._order_loading_spinner.stop()
        if hasattr(self, "_order_loading_progress"):
          try:
            self._order_loading_progress.stop()
          except Exception:
            pass
        self._order_loading_overlay.grid_remove()
    elif hasattr(self, "_order_loading_label"):
      if show:
        self._order_loading_label.grid()
      else:
        self._order_loading_label.grid_remove()

  def _start_loading_elapsed_timer(self) -> None:
    self._stop_loading_elapsed_timer()
    self._tick_loading_elapsed()

  def _stop_loading_elapsed_timer(self) -> None:
    job = getattr(self, "_loading_elapsed_job", None)
    if job is not None:
      try:
        self.root.after_cancel(job)
      except Exception:
        pass
      self._loading_elapsed_job = None

  def _tick_loading_elapsed(self) -> None:
    if not self._is_loading_overlay_visible():
      self._loading_elapsed_job = None
      return
    elapsed = int(time.time() - getattr(self, "_loading_started_at", time.time()))
    if elapsed >= 5 and hasattr(self, "_order_loading_detail"):
      base = self._loading_base_message or "Working…"
      fraction = self._loading_last_fraction
      if fraction is not None:
        text = f"{base} ({int(fraction * 100)}%) — {elapsed}s elapsed"
      else:
        text = f"{base} — {elapsed}s elapsed"
      try:
        self._order_loading_detail.configure(text=text)
      except Exception:
        pass
    self._loading_elapsed_job = self.root.after(1000, self._tick_loading_elapsed)

  def _show_order_empty_state(self, show: bool) -> None:
    """Show or hide the empty shelf placeholder message."""
    if hasattr(self, "_order_empty_label"):
      if show:
        self._order_empty_label.grid()
      else:
        self._order_empty_label.grid_remove()

  def _clear_treeview(self):
    """Clear all items from the treeview."""
    for item in self.order_tree.get_children():
      self.order_tree.delete(item)

  def _apply_manual_order_if_enabled(self, result: BuildResult):
    """Apply manual ordering if enabled and update manual order manager."""
    rows = result.rows_sorted
    if self.v_manual_order_enabled.get():
      if result.username:
        self._manual_order.set_username(result.username)
      rows = self._manual_order.apply_order(rows)
    return rows

  def _show_or_hide_price_column(self):
    """Show or hide the Price column based on the setting."""
    show_prices = self.v_show_prices.get()
    if show_prices:
      self.order_tree.column("Price", width=80, minwidth=70, stretch=False)
    else:
      self.order_tree.column("Price", width=0, minwidth=0, stretch=False)

  def _get_placeholder_image(self):
    """Get placeholder image for items without thumbnails."""
    if self._thumbnails_enabled:
      return self._thumbnail_cache.get_placeholder()
    return None

  def _populate_treeview_rows(self, rows, placeholder):
    """Populate the treeview with rows and images."""
    show_prices = self.v_show_prices.get()
    for i, row in enumerate(rows):
      tag = "row_odd" if i % 2 == 1 else "row_even"
      price_str = self._format_price(row, show_prices)
      label_str = f"{row.label} {row.catno}".strip() if row.label or row.catno else ""
      year_str = str(row.year) if row.year else ""
      values = (
        str(i + 1),
        row.artist_display,
        row.title,
        year_str,
        label_str,
        price_str,
      )
      img = self._get_row_image(row, placeholder)
      if img:
        self.order_tree.insert("", "end", image=img, values=values, tags=(tag,))
      else:
        self.order_tree.insert("", "end", values=values, tags=(tag,))

  def _format_price(self, row, show_prices):
    """Format the price string for a row."""
    if show_prices and row.lowest_price is not None:
      return f"{row.lowest_price:.0f} {row.price_currency}"
    elif show_prices:
      return "[Not listed]"
    else:
      return ""

  def _get_row_image(self, row, placeholder):
    """Get the thumbnail image for a row, or placeholder if missing."""
    img = None
    if self._thumbnails_enabled:
      if row.release_id:
        img = self._thumbnail_cache.load_photo(row.release_id)
      if img is None:
        img = placeholder
    return img

  def _download_missing_thumbnails(self, rows: list) -> None:
    """Start background download of missing thumbnails."""
    # Collect rows that need thumbnail downloads
    to_download = []
    for row in rows:
      if row.release_id and row.thumb_url:
        if not self._thumbnail_cache.has_cached(row.release_id):
          to_download.append((row.release_id, row.thumb_url))
    
    if not to_download:
      return
    
    # Get current headers
    try:
      headers = discogs_headers(self.v_token.get(), self.v_user_agent.get())
    except Exception:
      headers = {"User-Agent": "Mozilla/5.0"}
    
    # Download in background thread
    def download_worker():
      for release_id, thumb_url in to_download:
        try:
          self._thumbnail_cache.download_thumbnail(release_id, thumb_url, headers)
        except Exception:
          pass  # Ignore download failures
      # After downloads complete, refresh display on main thread
      self.root.after(0, self._refresh_thumbnails)
    
    thread = threading.Thread(target=download_worker, daemon=True)
    thread.start()
  
  def _refresh_thumbnails(self) -> None:
    """Refresh the treeview to show newly downloaded thumbnails."""
    if not self._thumbnails_enabled:
      return
    
    # Update shelf order tree items with thumbnails
    if self._last_result:
      items = self.order_tree.get_children()
      rows = self._tree_rows
      
      for i, (item, row) in enumerate(zip(items, rows)):
        if row.release_id:
          img = self._thumbnail_cache.load_photo(row.release_id)
          if img:
            self.order_tree.item(item, image=img)
    
    # Update wishlist tree items with thumbnails
    if hasattr(self, 'wishlist_tree') and hasattr(self, '_wishlist_rows'):
      items = self.wishlist_tree.get_children()
      rows = self._wishlist_rows
      
      for i, (item, row) in enumerate(zip(items, rows)):
        if row.release_id:
          img = self._thumbnail_cache.load_photo(row.release_id)
          if img:
            self.wishlist_tree.item(item, image=img)

  def _update_status_bar(self, result: BuildResult) -> None:
    """Update the status bar with collection info."""
    from datetime import datetime

    self._update_collection_count(result)
    self._update_last_sync()
    self._update_total_value_section(result)

  def _update_collection_count(self, result: BuildResult) -> None:
    count = len(self._filter_rows_by_format(result.rows_sorted))
    self.v_collection_count.set(f"{count} albums")

  def _update_last_sync(self) -> None:
    from datetime import datetime
    now = datetime.now()
    self.v_last_sync.set(f"Synced {now.strftime('%H:%M')}")

  def _update_total_value_section(self, result: BuildResult) -> None:
    filtered = self._filter_rows_by_format(result.rows_sorted)
    if self.v_show_prices.get() and filtered:
      total_value, priced_count, currency = self._calculate_total_value(filtered)
      if priced_count > 0:
        value_str = self._format_total_value(total_value, currency)
        self.v_total_value.set(f"~{value_str} ({priced_count} priced)")
        self._show_value_section()
      else:
        self._hide_value_section()
    else:
      self._hide_value_section()

  def _calculate_total_value(self, rows) -> tuple[float, int, str]:
    total_value = 0.0
    priced_count = 0
    currency = ""
    for row in rows:
      if row.lowest_price is not None:
        total_value += row.lowest_price
        priced_count += 1
        if not currency and row.price_currency:
          currency = row.price_currency
    return total_value, priced_count, currency

  def _format_total_value(self, total_value: float, currency: str) -> str:
    if total_value >= 1000:
      return f"{total_value:,.0f} {currency}"
    else:
      return f"{total_value:.0f} {currency}"

  def _show_value_section(self) -> None:
    if hasattr(self, '_value_sep'):
      self._value_sep.pack(side="left", padx=(16, 8))
    if hasattr(self, '_value_icon'):
      self._value_icon.pack(side="left", padx=(0, 4))
    if hasattr(self, '_value_label'):
      self._value_label.pack(side="left")

  def _hide_value_section(self) -> None:
    for attr in ['_value_sep', '_value_icon', '_value_label']:
      if hasattr(self, attr):
        getattr(self, attr).pack_forget()

  def _highlight_search(self) -> None:
    """Highlight matching rows in the Treeview based on search query."""
    q = (self.v_search.get() or "").strip().lower()
    self._reset_treeview_tags()
    if not q:
      self._set_match_count_label()
      return
    matches, first_match_item = self._find_and_highlight_matches(q)
    if matches == 0:
      self.v_match.set("No matches — try a different term")
    else:
      self.v_match.set(f"{matches} matches" if matches != 1 else "1 match")
    if first_match_item is not None:
      self.order_tree.see(first_match_item)
      self.order_tree.selection_set(first_match_item)

  def _reset_treeview_tags(self):
    """Reset all tags to default alternating colors."""
    for i, item in enumerate(self.order_tree.get_children()):
      tag = "row_odd" if i % 2 == 1 else "row_even"
      self.order_tree.item(item, tags=(tag,))

  def _set_match_count_label(self):
    """Set the match count label based on current rows."""
    if self._tree_rows:
      self.v_match.set(f"{len(self._tree_rows)} items")
    else:
      self.v_match.set("")

  def _find_and_highlight_matches(self, q: str):
    """Find and highlight matching rows, returning match count and first match item."""
    matches = 0
    first_match_item = None
    for i, item in enumerate(self.order_tree.get_children()):
      values = self.order_tree.item(item, "values")
      row_text = " ".join(str(v) for v in values[1:]).lower()
      if q in row_text:
        self.order_tree.item(item, tags=("search_match",))
        matches += 1
        if first_match_item is None:
          first_match_item = item
    return matches, first_match_item

  def _on_search_change(self) -> None:
    self._highlight_search()

  def _selected_formats(self) -> list[str]:
    """Return the list of format keys currently checked."""
    return [key for key, var in self.v_formats.items() if var.get()]

  def _filter_rows_by_format(self, rows):
    """Filter rows to those matching the selected format checkboxes."""
    return filter_rows_by_format(rows, set(self._selected_formats()))

  def _on_format_filter_change(self) -> None:
    """Persist selection and re-render the current result without re-fetching."""
    if getattr(self, "_settings", None) is not None:
      self._settings.update_format_checks_state()
    self._save_settings()
    if getattr(self, "_last_result", None) is not None:
      self._render_order(self._last_result)
      self._update_collection_count(self._last_result)
      self._update_total_value_section(self._last_result)

  def _get_cfg(self) -> AutoConfig:
    return AutoConfig(
      token=self.v_token.get().strip(),
      user_agent=self.v_user_agent.get().strip() or "VinylSorter/1.0 (+contact)",
      output_dir=self.v_output_dir.get().strip() or str(Path.cwd()),
      per_page=max(1, min(int(self.v_per_page.get() or 100), 100)),
      write_json=bool(self.v_json.get()),
      poll_seconds=max(15, int(self.v_poll.get() or POLL_SECONDS_DEFAULT)),
      show_prices=bool(self.v_show_prices.get()),
      currency=self.v_currency.get().strip() or "USD",
      sort_by=self.v_sort_by.get().strip() or "artist",
      oauth_access_token=(self._oauth_access_token or "").strip() or None,
      oauth_access_secret=(self._oauth_access_secret or "").strip() or None,
    )

  def _refresh_worker_cfg(self) -> None:
    """Capture settings for background threads. Call from the main thread only."""
    cfg = self._get_cfg()
    with self._worker_cfg_lock:
      self._worker_cfg = cfg

  def _get_worker_cfg(self) -> AutoConfig:
    """Thread-safe read of the last settings snapshot."""
    with self._worker_cfg_lock:
      if self._worker_cfg is None:
        raise RuntimeError("Worker config not initialized")
      return self._worker_cfg

  def _refresh_now(self) -> None:
    # Wake the watcher and force immediate check
    self._refresh_worker_cfg()
    self._log("Manual refresh requested.")
    self.v_status.set("Refresh requested…")
    self._show_order_loading_state(True)
    self._force_rebuild = True
    self._wake.set()

  def _stop_app(self) -> None:
    if messagebox.askyesno("Stop", "Stop auto-watching and close the app?"):
      self._stop.set()
      self.root.after(200, self.root.destroy)

  def _export_files(self) -> None:
    result = self._last_result
    if not result or not result.rows_sorted:
      messagebox.showinfo("Export", "No shelf order available yet. Wait for the first build, then try again.")
      return

    cfg = self._get_cfg()
    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Use the current display order (which respects manual ordering)
    rows_to_export = self._tree_rows if self._tree_rows else result.rows_sorted
    rows_to_export, truncated = apply_record_limit(list(rows_to_export))
    if truncated:
      if not messagebox.askyesno(
        "Free tier limit",
        f"Export includes the first {FREE_RECORD_LIMIT} records only.\n\nContinue?",
      ):
        return

    divider_mode = self._divider_mode_value()
    if divider_mode != "none" and not can_use_abc_dividers():
      divider_mode = "none"

    txt_path = out_dir / "vinyl_shelf_order.txt"
    csv_path = out_dir / "vinyl_shelf_order.csv"
    write_txt(
      rows_to_export,
      txt_path,
      divider_mode=divider_mode,
      align=False,
      show_country=False,
      show_price=bool(self.v_show_prices.get()),
    )
    write_csv(rows_to_export, csv_path)
    self._log(f"Exported: {txt_path.name}")
    self._log(f"Exported: {csv_path.name}")

    if cfg.write_json:
      json_path = out_dir / "vinyl_shelf_order.json"
      write_json(rows_to_export, json_path)
      self._log(f"Exported: {json_path.name}")
    
    # Note if manual order was used
    if self.v_manual_order_enabled.get():
      self._log("(Exported with manual ordering)")

    messagebox.showinfo("Export", f"Wrote files to:\n{out_dir}")
    self.v_status.set(f"Exported to: {out_dir}")

  def _print_current(self) -> None:
    if not self._tree_rows:
      messagebox.showinfo("Print", "Nothing to print yet. Wait for the first build.")
      return

    rows, truncated = apply_record_limit(list(self._tree_rows))
    if truncated:
      if not messagebox.askyesno(
        "Free tier limit",
        f"Print includes the first {FREE_RECORD_LIMIT} records only.\n\nContinue?",
      ):
        return

    if not messagebox.askyesno("Print", "Send the current shelf order to your default printer?"):
      return
    
    lines = generate_txt_lines(
      rows,
      divider_mode=self._divider_mode_value(),
      show_price=bool(self.v_show_prices.get()),
    )

    # Try Windows printing first, fall back to lpr
    tmp_path = None
    try:
      import tempfile
      with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        tmp_path = f.name
      
      # Windows: use notepad /p for printing
      import platform
      if platform.system() == "Windows":
        subprocess.run(["notepad", "/p", tmp_path], check=True)
      else:
        # Unix: use lpr
        subprocess.run(["lpr", tmp_path], check=True)
      
      self._log("Sent to printer.")
      self.v_status.set("Sent to printer.")
    except Exception as e:
      messagebox.showerror("Print", f"Printing failed: {e}")
      self.v_status.set("Print failed.")
    finally:
      if tmp_path and Path(tmp_path).exists():
        try:
          Path(tmp_path).unlink()
        except Exception:
          pass

  def _watch_loop(self) -> None:
    """Background thread: poll collection count; rebuild on change or manual refresh."""
    self._log("Watcher started.")
    self._set_status_async("Watching for changes…")

    def progress_callback(action: str, message: str | None, fraction: float | None = None):
      self._report_build_progress(action, message, fraction)

    while not self._stop.is_set():
      cfg = self._get_worker_cfg()
      try:
        if not self._has_valid_token(cfg):
          self._handle_missing_token(cfg)
          continue

        force = self._force_rebuild
        if force or self._last_count is None:
          self._log("Connecting to Discogs…")
          self._report_build_progress("update", "Connecting to Discogs…", 0.0)

        _, headers, session, username = self._get_user_info(cfg)
        self._log(f"Signed in as {username}. Checking collection size…")
        self._report_build_progress("update", "Checking collection size…", 0.01)
        count = get_collection_count(headers=headers, session=session, username=username)
        self._log(f"Discogs reports {count} items in collection.")
        self._force_rebuild = False

        if self._should_build_initial(force):
          self._handle_initial_build(cfg, count, progress_callback)
        elif count != self._last_count:
          self._handle_collection_changed(cfg, count, progress_callback)
        else:
          self._set_status_async(f"No changes. Polling every {cfg.poll_seconds}s")

      except Exception as e:
        self._handle_watch_exception(e)

      self._wake.clear()
      self._wake.wait(timeout=cfg.poll_seconds)

    self._log("Watcher stopped.")

  def _has_valid_token(self, cfg):
    return bool(
      cfg.token or os.environ.get("DISCOGS_TOKEN", "") or
      (cfg.oauth_access_token and cfg.oauth_access_secret)
    )

  def _oauth_signin_available(self) -> bool:
    from core.oauth_discogs import oauth_is_configured

    return oauth_is_configured()

  def _ensure_settings_visible(self) -> None:
    """Expand the settings sidebar if it is collapsed."""
    if getattr(self, "_settings_collapsed", False):
      self._toggle_settings_sidebar()

  def _prompt_first_run_auth(self) -> None:
    """First-run wizard, then optional sign-in when no Discogs auth is configured."""
    saved = load_config()
    if not saved.get("wizard_completed"):
      from gui.first_run_wizard import FirstRunWizard
      FirstRunWizard(self).run()
    if self._auth_prompt_shown:
      return
    cfg = self._get_cfg()
    if self._has_valid_token(cfg):
      return
    self._auth_prompt_shown = True
    if not self._oauth_signin_available():
      self._log("Discogs sign-in is not available in this build.")
      return
    if messagebox.askyesno(
      "Connect to Discogs",
      "Sign in with your Discogs account to load your vinyl collection.\n\n"
      "Your web browser will open. Click Approve on Discogs, then return here.",
    ):
      self._do_oauth_signin()
    else:
      self._log("No Discogs sign-in yet — use Sign in with Discogs in Settings.")

  def _handle_missing_token(self, cfg):
    self._log("Error: Not signed in to Discogs. Click Sign in with Discogs in Settings.")
    self._set_status_async("Error: Sign in required (see Settings)")
    self._report_build_progress(
      "error",
      "Not signed in. Use Sign in with Discogs in Settings.",
      None,
    )
    self._wake.clear()
    self._wake.wait(timeout=cfg.poll_seconds)

  def _update_wishlist_background(self, cfg) -> None:
    """Refresh wishlist after the shelf order build so collection load is not blocked."""
    def work() -> None:
      try:
        from core.wishlist import save_wishlist
        from core.api import fetch_discogs_wantlist

        _, headers, session, _ = self._get_user_info(cfg)
        if not session and not (cfg.token or "").strip():
          return
        self._log("Updating wishlist from Discogs…")
        wantlist = fetch_discogs_wantlist(
          token=(cfg.token or "").strip() or None,
          session=session,
          user_agent=cfg.user_agent,
        )
        save_wishlist(wantlist)
        self._log(f"Wishlist updated from Discogs. {len(wantlist)} items.")
        try:
          if hasattr(self, "refresh_wishlist_tree"):
            self.root.after(0, self.refresh_wishlist_tree)
        except Exception:
          pass
      except Exception as e:
        self._log(f"Failed to update wishlist from Discogs: {e}")

    threading.Thread(target=work, daemon=True, name="wishlist-sync").start()

  def _get_user_info(self, cfg):
    """Return (token, headers, session, username). Uses OAuth if available."""
    _, headers, session, username = _get_user_headers(cfg, self._log)
    token = cfg.token or os.environ.get("DISCOGS_TOKEN", "") or None
    if session:
      return token, None, session, username
    return token, headers, None, username

  def _should_build_initial(self, force):
    return self._last_count is None or force

  def _handle_initial_build(self, cfg, count, progress_callback):
    if self._last_count is None:
      self._last_count = count
      self._log(f"Initial collection count: {count}")
    else:
      self._log(f"Forced refresh. Collection count: {count}")
    self._report_build_progress("update", f"Found {count} items — starting download…", 0.02)
    self._log("Building shelf order…")
    self._set_status_async("Building…")
    result = build_once(cfg, self._log, progress_callback, self._collection_cache, self.progress_q)
    self.result_q.put(result)
    self._last_built_at = time.time()
    self._log(f"Build complete. Items: {len(result.rows_sorted)}")
    self._set_status_async(f"Built {len(result.rows_sorted)} items. Polling every {cfg.poll_seconds}s")
    self._update_wishlist_background(cfg)

  def _handle_collection_changed(self, cfg, count, progress_callback):
    self._log(f"Collection changed: {self._last_count} → {count}")
    self._last_count = count
    self._log("Rebuilding shelf order…")
    self._set_status_async("Rebuilding…")
    self._report_build_progress("update", f"Collection changed — rebuilding {count} items…", 0.02)
    result = build_once(cfg, self._log, progress_callback, self._collection_cache, self.progress_q)
    self.result_q.put(result)
    self._last_built_at = time.time()
    self._log(f"Build complete. Items: {len(result.rows_sorted)}")
    self._set_status_async(f"Built {len(result.rows_sorted)} items. Polling every {cfg.poll_seconds}s")

  def _handle_watch_exception(self, e):
    self._log(f"Error: {e}")
    self._log(traceback.format_exc())
    self._set_status_async("Error (see Log tab).")
    self._report_build_progress("error", str(e), None)


def main() -> None:
  def _log_crash(exc_type, exc, tb):
    try:
      log_path = project_root() / "crash.log"
      with log_path.open("a", encoding="utf-8") as f:
        f.write("\n---\n")
        traceback.print_exception(exc_type, exc, tb, file=f)
    except Exception:
      pass
    sys.__excepthook__(exc_type, exc, tb)

  sys.excepthook = _log_crash

  # Set CustomTkinter appearance and theme
  ctk.set_appearance_mode("dark")  # "dark" or "light"
  ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"

  # Create CustomTkinter root window
  root = ctk.CTk()
  root.title(f"{APP_NAME} {__version__}")

  App(root)
  root.mainloop()


if __name__ == "__main__":
  main()
