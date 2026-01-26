#!/usr/bin/env python3
"""Discogs Auto-Sort GUI

A fresh, minimal GUI that:
- Watches your Discogs collection for changes (polls item count).
- Regenerates shelf order automatically when it changes.
- Provides a "Refresh Now" button to force an immediate re-check + rebuild.

It reuses the core logic in discogs_app.py for fetching, sorting, and writing outputs.
Token discovery order:
- GUI Token field (if provided)
- DISCOGS_TOKEN env var
- .env (python-dotenv), via discogs_app.get_token

Outputs (default):
- vinyl_shelf_order.txt
- vinyl_shelf_order.csv
- optional JSON if enabled

Note: This is a polling-based approach because Discogs doesn’t provide push webhooks for
personal collections.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

# Use ttkbootstrap for modern rounded widgets
try:
  import ttkbootstrap as ttk
  from ttkbootstrap.constants import *
  TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
  from tkinter import ttk
  TTKBOOTSTRAP_AVAILABLE = False

from tkinter import Tk, StringVar, BooleanVar, IntVar, filedialog, messagebox

import discogs_app as core


POLL_SECONDS_DEFAULT = 300  # 5 minutes
CONFIG_FILE = Path(__file__).parent / ".discogs_config.json"
# Simple key for obfuscation (not meant to be cryptographically secure, just prevents casual viewing)
_OBFUSCATE_KEY = b"DiscogsVinylSorter2026"


def _obfuscate(text: str) -> str:
  """Obfuscate a string to prevent casual viewing."""
  if not text:
    return ""
  data = text.encode("utf-8")
  key = _OBFUSCATE_KEY
  result = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
  return base64.b64encode(result).decode("ascii")


def _deobfuscate(encoded: str) -> str:
  """Reverse the obfuscation."""
  if not encoded:
    return ""
  try:
    data = base64.b64decode(encoded.encode("ascii"))
    key = _OBFUSCATE_KEY
    result = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return result.decode("utf-8")
  except Exception:
    return ""


def load_config() -> dict:
  """Load saved configuration from file."""
  try:
    if CONFIG_FILE.exists():
      with CONFIG_FILE.open("r", encoding="utf-8") as f:
        config = json.load(f)
        # Deobfuscate the token if present
        if "token_encrypted" in config:
          config["token"] = _deobfuscate(config.pop("token_encrypted"))
        return config
  except Exception:
    pass
  return {}


def save_config(config: dict) -> None:
  """Save configuration to file."""
  try:
    # Make a copy and encrypt the token
    save_data = config.copy()
    if "token" in save_data:
      save_data["token_encrypted"] = _obfuscate(save_data.pop("token"))
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
      json.dump(save_data, f, indent=2)
  except Exception:
    pass


# Collection cache file
CACHE_FILE = Path(__file__).parent / ".discogs_collection_cache.json"
PRICE_CACHE_MAX_AGE_SECONDS = 86400 * 7  # 7 days before prices are considered stale


class CollectionCache:
  """Local cache for Discogs collection data and prices.
  
  Stores:
  - Release info (artist, title, year, label, etc.)
  - Price info with timestamp
  - Avoids re-fetching unchanged releases
  """
  
  def __init__(self, cache_file: Path = CACHE_FILE):
    self.cache_file = cache_file
    self._data: dict = {
      "version": 1,
      "username": None,
      "releases": {},  # keyed by release_id
      "last_full_fetch": None,
    }
    self._load()
  
  def _load(self) -> None:
    """Load cache from disk."""
    try:
      if self.cache_file.exists():
        with self.cache_file.open("r", encoding="utf-8") as f:
          loaded = json.load(f)
          if loaded.get("version") == 1:
            self._data = loaded
    except Exception:
      pass
  
  def _save(self) -> None:
    """Save cache to disk."""
    try:
      with self.cache_file.open("w", encoding="utf-8") as f:
        json.dump(self._data, f, indent=2)
    except Exception:
      pass
  
  def get_username(self) -> str | None:
    """Get cached username."""
    return self._data.get("username")
  
  def set_username(self, username: str) -> None:
    """Set username and clear cache if changed."""
    if self._data.get("username") != username:
      # Different user - clear the cache
      self._data = {
        "version": 1,
        "username": username,
        "releases": {},
        "last_full_fetch": None,
      }
      self._save()
  
  def get_release(self, release_id: int) -> dict | None:
    """Get cached release data."""
    return self._data["releases"].get(str(release_id))
  
  def set_release(self, release_id: int, data: dict) -> None:
    """Cache a release's data."""
    self._data["releases"][str(release_id)] = {
      **data,
      "cached_at": time.time(),
    }
  
  def get_price(self, release_id: int, currency: str) -> tuple[float | None, int | None, bool]:
    """Get cached price info for a release.
    
    Returns: (lowest_price, num_for_sale, is_stale)
    """
    release = self._data["releases"].get(str(release_id))
    if not release:
      return None, None, True
    
    prices = release.get("prices", {})
    price_data = prices.get(currency)
    if not price_data:
      return None, None, True
    
    # Check if price is stale
    price_time = price_data.get("fetched_at", 0)
    is_stale = (time.time() - price_time) > PRICE_CACHE_MAX_AGE_SECONDS
    
    return price_data.get("lowest_price"), price_data.get("num_for_sale"), is_stale
  
  def set_price(self, release_id: int, currency: str, lowest_price: float | None, num_for_sale: int | None) -> None:
    """Cache price info for a release."""
    release_key = str(release_id)
    if release_key not in self._data["releases"]:
      self._data["releases"][release_key] = {"cached_at": time.time()}
    
    if "prices" not in self._data["releases"][release_key]:
      self._data["releases"][release_key]["prices"] = {}
    
    self._data["releases"][release_key]["prices"][currency] = {
      "lowest_price": lowest_price,
      "num_for_sale": num_for_sale,
      "fetched_at": time.time(),
    }
  
  def has_all_releases(self, release_ids: list[int]) -> bool:
    """Check if we have cached data for all given release IDs."""
    for rid in release_ids:
      if str(rid) not in self._data["releases"]:
        return False
    return True
  
  def get_cached_count(self) -> int:
    """Get number of cached releases."""
    return len(self._data["releases"])
  
  def get_prices_needing_fetch(self, release_ids: list[int], currency: str) -> list[int]:
    """Get release IDs that need price fetching (missing or stale)."""
    need_fetch = []
    for rid in release_ids:
      _, _, is_stale = self.get_price(rid, currency)
      if is_stale:
        need_fetch.append(rid)
    return need_fetch
  
  def save(self) -> None:
    """Explicitly save cache to disk."""
    self._save()
  
  def clear_prices(self, currency: str = None) -> int:
    """Clear cached prices, forcing re-fetch.
    
    Args:
      currency: If specified, only clear prices for this currency.
                If None, clear all prices.
    
    Returns:
      Number of releases affected.
    """
    count = 0
    for release_key, release_data in self._data["releases"].items():
      if "prices" in release_data:
        if currency:
          if currency in release_data["prices"]:
            del release_data["prices"][currency]
            count += 1
        else:
          release_data["prices"] = {}
          count += 1
    self._save()
    return count
  
  def clear(self) -> None:
    """Clear all cached data."""
    self._data = {
      "version": 1,
      "username": None,
      "releases": {},
      "last_full_fetch": None,
    }
    self._save()


@dataclass
class AutoConfig:
  token: str
  user_agent: str
  output_dir: str
  per_page: int
  write_json: bool
  poll_seconds: int
  show_prices: bool = False
  currency: str = "USD"
  sort_by: str = "artist"


def get_collection_count(headers: dict[str, str], username: str) -> int:
  """Fetch collection size cheaply via pagination metadata."""
  url = f"{core.API_BASE}/users/{username}/collection/folders/0/releases"
  data = core.api_get(url, headers, params={"page": "1", "per_page": "1"}).json()
  return int(data.get("pagination", {}).get("items", 0))


@dataclass
class BuildResult:
  username: str
  rows_sorted: list[core.ReleaseRow]
  lines: list[str]


class ProgressDialog:
  """A modal progress dialog with a spinning vinyl record animation."""
  
  def __init__(self, parent, title: str = "Please Wait", message: str = "Loading..."):
    import tkinter as tk
    from tkinter import scrolledtext
    import math
    
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
    
    # Title label at top
    self.title_label = tk.Label(
      self.top,
      text="🎵 Fetching Album Prices",
      font=("Segoe UI Semibold", 15),
      bg="#16213e",
      fg="#6c63ff"
    )
    self.title_label.pack(pady=(20, 8))
    
    # Main content frame (record + info side by side)
    content_frame = tk.Frame(self.top, bg="#16213e")
    content_frame.pack(fill="x", padx=24, pady=(8, 12))
    
    # Left side: Spinning record canvas
    self.canvas = tk.Canvas(
      content_frame,
      width=100,
      height=100,
      bg="#16213e",
      highlightthickness=0
    )
    self.canvas.pack(side="left", padx=(0, 20))
    
    # Right side: Message and progress
    info_frame = tk.Frame(content_frame, bg="#16213e")
    info_frame.pack(side="left", fill="both", expand=True)
    
    self.msg_label = tk.Label(
      info_frame,
      text=message,
      font=("Segoe UI", 10),
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
      font=("Segoe UI Semibold", 12),
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
      font=("Segoe UI Semibold", 10),
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
      font=("Cascadia Code", 9),
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
    
    # Animation state
    self.angle = 0
    self.spinning = True
    
    # Draw the vinyl record
    self._draw_record()
    
    # Start animation
    self._animate()
    
    # Prevent closing
    self.top.protocol("WM_DELETE_WINDOW", lambda: None)
    
    # Center on parent
    self.top.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.top.winfo_width() // 2)
    y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.top.winfo_height() // 2)
    self.top.geometry(f"+{x}+{y}")
  
  def _draw_record(self) -> None:
    """Draw the vinyl record on the canvas with visible spinning indicator."""
    import math
    cx, cy = 50, 50  # Center (smaller record)
    
    # Clear canvas
    self.canvas.delete("all")
    
    # Outer edge shadow
    self.canvas.create_oval(3, 3, 97, 97, fill="#151525", outline="")
    
    # Outer edge (slightly lighter)
    self.canvas.create_oval(2, 2, 96, 96, fill="#2a2a3e", outline="#3a3a4e", width=2)
    
    # Main record (black vinyl)
    self.canvas.create_oval(5, 5, 95, 95, fill="#1a1a1a", outline="#0a0a0a", width=1)
    
    # Grooves (concentric circles)
    for r in range(42, 15, -4):
      self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#252525", width=1)
    
    # Center label (purple)
    self.canvas.create_oval(cx-12, cy-12, cx+12, cy+12, fill="#6c63ff", outline="#5a52dd", width=2)
    
    # Spindle hole
    self.canvas.create_oval(cx-3, cy-3, cx+3, cy+3, fill="#1a1a2e", outline="#0a0a1e", width=1)
    
    # SPINNING INDICATOR - A bright white/silver highlight that rotates
    angle_rad = math.radians(self.angle)
    
    # Bright spinning highlight line (very visible)
    x1 = cx + 14 * math.cos(angle_rad)
    y1 = cy + 14 * math.sin(angle_rad)
    x2 = cx + 42 * math.cos(angle_rad)
    y2 = cy + 42 * math.sin(angle_rad)
    self.canvas.create_line(x1, y1, x2, y2, fill="#ffffff", width=3, capstyle="round")
    
    # Secondary highlight (dimmer, offset by 120 degrees)
    angle_rad2 = math.radians(self.angle + 120)
    x1 = cx + 14 * math.cos(angle_rad2)
    y1 = cy + 14 * math.sin(angle_rad2)
    x2 = cx + 42 * math.cos(angle_rad2)
    y2 = cy + 42 * math.sin(angle_rad2)
    self.canvas.create_line(x1, y1, x2, y2, fill="#888888", width=2, capstyle="round")
    
    # Third highlight (dimmest, offset by 240 degrees)
    angle_rad3 = math.radians(self.angle + 240)
    x1 = cx + 14 * math.cos(angle_rad3)
    y1 = cy + 14 * math.sin(angle_rad3)
    x2 = cx + 42 * math.cos(angle_rad3)
    y2 = cy + 42 * math.sin(angle_rad3)
    self.canvas.create_line(x1, y1, x2, y2, fill="#444444", width=1, capstyle="round")
  
  def _animate(self) -> None:
    """Animate the spinning record."""
    if self.spinning:
      self.angle = (self.angle + 10) % 360  # Rotate 10 degrees per frame
      self._draw_record()
      try:
        self.top.after(40, self._animate)  # 25 FPS for smoother animation
      except Exception:
        pass  # Dialog may have been closed
  
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
      self.spinning = False
      self.top.grab_release()
      self.top.destroy()
    except Exception:
      pass


class ToolTip:
  """Modern tooltip that appears on hover with a slight delay."""
  
  def __init__(self, widget, text: str, delay: int = 400, wraplength: int = 280):
    self.widget = widget
    self.text = text
    self.delay = delay
    self.wraplength = wraplength
    self.tip_window = None
    self.id_after = None
    
    widget.bind("<Enter>", self._on_enter)
    widget.bind("<Leave>", self._on_leave)
    widget.bind("<ButtonPress>", self._on_leave)
  
  def _on_enter(self, event=None):
    self._cancel()
    self.id_after = self.widget.after(self.delay, self._show_tip)
  
  def _on_leave(self, event=None):
    self._cancel()
    self._hide_tip()
  
  def _cancel(self):
    if self.id_after:
      self.widget.after_cancel(self.id_after)
      self.id_after = None
  
  def _show_tip(self):
    if self.tip_window:
      return
    
    import tkinter as tk
    
    x = self.widget.winfo_rootx() + 20
    y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
    
    self.tip_window = tw = tk.Toplevel(self.widget)
    tw.wm_overrideredirect(True)
    tw.wm_geometry(f"+{x}+{y}")
    
    # Modern dark tooltip style
    tw.configure(bg="#1a1a2e")
    
    frame = tk.Frame(tw, bg="#1a1a2e", bd=1, relief="solid", highlightbackground="#6c63ff", highlightthickness=1)
    frame.pack()
    
    label = tk.Label(
      frame,
      text=self.text,
      justify="left",
      background="#1a1a2e",
      foreground="#eaeaea",
      font=("Segoe UI", 9),
      wraplength=self.wraplength,
      padx=10,
      pady=6,
    )
    label.pack()
  
  def _hide_tip(self):
    if self.tip_window:
      self.tip_window.destroy()
      self.tip_window = None
  
  def update_text(self, new_text: str):
    """Update tooltip text dynamically."""
    self.text = new_text


def build_once(cfg: AutoConfig, log: callable, progress_callback: callable = None, cache: CollectionCache = None) -> BuildResult:
  """Build the shelf order once.
  
  Args:
    cfg: Configuration
    log: Logging callback
    progress_callback: Optional callback for progress updates - called with (action, message)
                       where action is 'show', 'update', 'message', or 'close'
    cache: Optional collection cache for storing/retrieving release and price data
  """
  token = core.get_token(cfg.token or None)
  headers = core.discogs_headers(token, cfg.user_agent)
  ident = core.get_identity(headers)
  username = ident.get("username")
  if not username:
    raise RuntimeError("Could not determine username from token.")

  log(f"User: {username}")
  
  # Update cache with username (clears if different user)
  if cache:
    cache.set_username(username)

  out_dir = Path(cfg.output_dir)
  out_dir.mkdir(parents=True, exist_ok=True)

  rows = core.collect_lp_rows(
    headers=headers,
    username=username,
    per_page=max(1, min(int(cfg.per_page), 100)),
    max_pages=None,
    extra_articles=[],
    lp_strict=False,
    lp_probable=False,
    debug_stats=None,
    last_name_first=True,
    lnf_allow_3=False,
    lnf_exclude=set(),
    lnf_safe_bands=True,
    collect_exclusions=False,
  )

  if not rows:
    log("No matching LPs found.")
    return BuildResult(username=username, rows_sorted=[], lines=[])

  # Determine if we need prices (for display or sorting)
  need_prices = cfg.show_prices or cfg.sort_by in ("price_asc", "price_desc")
  
  # Fetch prices if needed
  if need_prices:
    # First, populate from cache where available
    releases_needing_fetch = []
    cached_count = 0
    
    if cache:
      for row in rows:
        if row.release_id:
          lowest, num_for_sale, is_stale = cache.get_price(row.release_id, cfg.currency)
          if not is_stale and lowest is not None:
            # Use cached price
            row.lowest_price = lowest
            row.median_price = lowest
            row.num_for_sale = num_for_sale
            row.price_currency = cfg.currency
            cached_count += 1
          else:
            releases_needing_fetch.append(row)
        else:
          releases_needing_fetch.append(row)
    else:
      releases_needing_fetch = [r for r in rows if r.release_id]
    
    if cached_count > 0:
      log(f"Loaded {cached_count} prices from cache.")
    
    # Only fetch prices we don't have cached
    if releases_needing_fetch:
      total_to_fetch = len([r for r in releases_needing_fetch if r.release_id])
      log(f"Fetching {total_to_fetch} prices ({cfg.currency})...")
      
      # Show progress dialog
      if progress_callback:
        progress_callback("show", f"Fetching {total_to_fetch} album prices in {cfg.currency}.\n({cached_count} loaded from cache)")
      
      # Create a progress callback that updates both log and dialog
      fetched_count = [0]  # Use list to allow mutation in closure
      def price_progress(msg: str):
        fetched_count[0] += 1
        log(msg)
        if progress_callback:
          progress_callback("update", f"[{fetched_count[0]}/{total_to_fetch}] {msg}")
      
      # Fetch prices for releases not in cache
      core.fetch_prices_for_rows(headers, releases_needing_fetch, currency=cfg.currency, log_callback=price_progress, debug=False)
      
      # Update cache with newly fetched prices
      if cache:
        for row in releases_needing_fetch:
          if row.release_id and row.lowest_price is not None:
            cache.set_price(row.release_id, cfg.currency, row.lowest_price, row.num_for_sale)
          elif row.release_id:
            # Cache "not listed" as well (lowest_price=None means not for sale)
            cache.set_price(row.release_id, cfg.currency, None, 0)
        cache.save()
      
      log("Price fetch complete.")
      
      # Close progress dialog
      if progress_callback:
        progress_callback("close", None)
    else:
      log("All prices loaded from cache.")
  
  # Sort the rows
  rows_sorted = core.sort_rows(rows, "normal", sort_by=cfg.sort_by)
  
  lines = core.generate_txt_lines(rows_sorted, dividers=False, align=False, show_country=False, show_price=need_prices)
  return BuildResult(username=username, rows_sorted=rows_sorted, lines=lines)


class App:
  def __init__(self, root: Tk) -> None:
    self.root = root
    root.title("Discogs Auto-Sort")
    try:
      root.minsize(900, 650)
    except Exception:
      pass

    # Dark mode toggle
    self.v_dark_mode = BooleanVar(value=True)

    # Use ttkbootstrap theming if available
    if TTKBOOTSTRAP_AVAILABLE:
      # Use 'darkly' theme for dark mode (has nice rounded corners)
      self.style = ttk.Style(theme="darkly")
    else:
      self.style = ttk.Style()
      try:
        if "clam" in self.style.theme_names():
          self.style.theme_use("clam")
      except Exception:
        pass

    # Palette (best-effort; note: macOS may still use native button chrome)
    self._dark_colors = {
      "bg": "#1a1a2e",        # deep navy
      "panel": "#16213e",     # dark blue
      "panel2": "#0f0f1a",    # darker
      "text": "#eaeaea",      # light gray
      "muted": "#8892b0",     # muted blue-gray
      "accent": "#6c63ff",    # purple accent
      "accent2": "#00d9ff",   # cyan accent
      "accent3": "#ff6b6b",   # coral/red accent
      "success": "#00c853",   # green
      "warn": "#ffab00",      # amber
      "order_bg": "#1e2746",  # slightly lighter navy
      "order_fg": "#eaeaea",  # light text
      "button_bg": "#6c63ff", # purple button
      "button_fg": "#ffffff", # white text
      "button_hover": "#5a52d5", # darker purple on hover
    }
    self._light_colors = {
      "bg": "#f0f4f8",        # light blue-gray
      "panel": "#ffffff",     # white
      "panel2": "#e8eef4",    # light gray-blue
      "text": "#1a1a2e",      # dark text
      "muted": "#64748b",     # muted gray
      "accent": "#6c63ff",    # purple accent
      "accent2": "#0891b2",   # teal accent
      "accent3": "#e11d48",   # rose accent
      "success": "#16a34a",   # green
      "warn": "#d97706",      # amber
      "order_bg": "#ffffff",  # white
      "order_fg": "#1a1a2e",  # dark text
      "button_bg": "#6c63ff", # purple button
      "button_fg": "#ffffff", # white text
      "button_hover": "#5a52d5", # darker purple on hover
    }
    self._colors = self._dark_colors.copy()

    # Configure custom styles
    self._configure_styles()

    # Load saved configuration
    saved_cfg = load_config()

    self.v_token = StringVar(value=saved_cfg.get("token", ""))
    self.v_show_token = BooleanVar(value=False)
    self.v_user_agent = StringVar(value=saved_cfg.get("user_agent", "VinylSorter/1.0 (+contact)"))
    self.v_output_dir = StringVar(value=saved_cfg.get("output_dir", str(Path.cwd())))
    self.v_per_page = IntVar(value=saved_cfg.get("per_page", 100))
    self.v_json = BooleanVar(value=saved_cfg.get("write_json", False))
    self.v_poll = IntVar(value=saved_cfg.get("poll_seconds", POLL_SECONDS_DEFAULT))
    # Always start with prices OFF - user must enable during session
    self.v_show_prices = BooleanVar(value=False)
    self.v_currency = StringVar(value=saved_cfg.get("currency", "USD"))
    self.v_sort_by = StringVar(value=saved_cfg.get("sort_by", "artist"))
    
    # Initialize the collection cache
    self._collection_cache = CollectionCache()

    # Auto-save settings when they change
    self.v_token.trace_add("write", lambda *_: self._save_settings())
    self.v_user_agent.trace_add("write", lambda *_: self._save_settings())
    self.v_output_dir.trace_add("write", lambda *_: self._save_settings())
    self.v_json.trace_add("write", lambda *_: self._save_settings())
    self.v_poll.trace_add("write", lambda *_: self._save_settings())
    self.v_show_prices.trace_add("write", lambda *_: self._save_settings())
    self.v_currency.trace_add("write", lambda *_: self._save_settings())
    self.v_sort_by.trace_add("write", lambda *_: self._save_settings())

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
    self.progress_q: queue.Queue[tuple[str, str | None]] = queue.Queue()  # (action, message)
    self._progress_dialog: ProgressDialog | None = None

    self._build_ui(root)
    self._setup_keyboard_shortcuts()
    self._pump_queues()

    # Start watching immediately
    threading.Thread(target=self._watch_loop, daemon=True).start()

  def _configure_styles(self) -> None:
    """Configure custom ttk styles for a modern, professional look."""
    c = self._colors
    
    # If using ttkbootstrap, let it handle styling for consistent backgrounds
    if TTKBOOTSTRAP_AVAILABLE:
      # Don't override label/frame backgrounds - let ttkbootstrap handle it
      # This ensures consistent colors across all widgets
      return
    
    # Fallback: standard ttk styling (no rounded corners)
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
                         font=("Segoe UI", 10))
    self.style.configure("Header.TLabel",
                         background=c["bg"],
                         foreground=c["text"],
                         font=("Segoe UI Semibold", 18))
    self.style.configure("Subtitle.TLabel",
                         background=c["bg"],
                         foreground=c["muted"],
                         font=("Segoe UI", 11))
    
    # Card/LabelFrame styles - softer look
    self.style.configure("Card.TLabelframe", 
                         background=c["panel"],
                         bordercolor=c["panel2"],
                         lightcolor=c["panel"],
                         darkcolor=c["panel"],
                         relief="flat",
                         borderwidth=0)
    self.style.configure("Card.TLabelframe.Label", 
                         foreground=c["accent"],
                         background=c["panel"],
                         font=("Segoe UI Semibold", 11))
    
    # Primary button style - more rounded feel with padding
    self.style.configure("Primary.TButton",
                         background=c["accent"],
                         foreground=c["button_fg"],
                         borderwidth=0,
                         focuscolor=c["accent"],
                         lightcolor=c["accent"],
                         darkcolor=c["accent"],
                         padding=(20, 12),
                         font=("Segoe UI Semibold", 10))
    self.style.map("Primary.TButton",
                   background=[("active", c["button_hover"]), ("pressed", c["button_hover"]), ("disabled", c["muted"])],
                   foreground=[("active", c["button_fg"]), ("disabled", "#888888")])
    
    # Success button style (green) - matching rounded feel
    self.style.configure("Success.TButton",
                         background=c["success"],
                         foreground="#ffffff",
                         borderwidth=0,
                         lightcolor=c["success"],
                         darkcolor=c["success"],
                         padding=(20, 12),
                         font=("Segoe UI Semibold", 10))
    self.style.map("Success.TButton",
                   background=[("active", "#00a844"), ("pressed", "#00a844")])
    
    # Secondary button style - subtle
    self.style.configure("Secondary.TButton",
                         background=c["panel2"],
                         foreground=c["text"],
                         borderwidth=0,
                         lightcolor=c["panel2"],
                         darkcolor=c["panel2"],
                         padding=(16, 10),
                         font=("Segoe UI", 10))
    self.style.map("Secondary.TButton",
                   background=[("active", c["order_bg"])])
    
    # Danger button style (red) - matching rounded feel
    self.style.configure("Danger.TButton",
                         background=c["accent3"],
                         foreground="#ffffff",
                         borderwidth=0,
                         lightcolor=c["accent3"],
                         darkcolor=c["accent3"],
                         padding=(20, 12),
                         font=("Segoe UI Semibold", 10))
    self.style.map("Danger.TButton",
                   background=[("active", "#c41840"), ("pressed", "#c41840")])
    
    # Regular button - clean look
    self.style.configure("TButton",
                         background=c["panel2"],
                         foreground=c["text"],
                         borderwidth=0,
                         lightcolor=c["panel2"],
                         darkcolor=c["panel2"],
                         focuscolor=c["panel2"],
                         padding=(16, 10),
                         font=("Segoe UI", 10))
    self.style.map("TButton",
                   background=[("active", c["order_bg"]), ("pressed", c["order_bg"])])
    
    # Entry style - more padding for cleaner look
    self.style.configure("TEntry",
                         fieldbackground=c["order_bg"],
                         foreground=c["text"],
                         insertcolor=c["text"],
                         borderwidth=0,
                         lightcolor=c["order_bg"],
                         darkcolor=c["order_bg"],
                         relief="flat",
                         padding=10)
    self.style.map("TEntry",
                   fieldbackground=[("focus", c["order_bg"])],
                   lightcolor=[("focus", c["accent"])],
                   darkcolor=[("focus", c["accent"])])
    
    # Combobox style - clean dropdown
    self.style.configure("TCombobox",
                         fieldbackground=c["order_bg"],
                         background=c["order_bg"],
                         foreground=c["text"],
                         arrowcolor=c["accent"],
                         borderwidth=0,
                         lightcolor=c["order_bg"],
                         darkcolor=c["order_bg"],
                         selectbackground=c["accent"],
                         selectforeground="#ffffff",
                         padding=8)
    self.style.map("TCombobox",
                   fieldbackground=[("readonly", c["order_bg"]), ("focus", c["order_bg"])],
                   foreground=[("readonly", c["text"])],
                   background=[("readonly", c["order_bg"]), ("active", c["order_bg"])],
                   arrowcolor=[("active", c["accent2"])])
    
    # Also configure the dropdown listbox via option_add
    try:
      self.root.option_add("*TCombobox*Listbox.background", c["order_bg"])
      self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
      self.root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
      self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
      self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))
    except Exception:
      pass
    
    # Checkbutton style - clean modern look
    self.style.configure("TCheckbutton",
                         background=c["panel"],
                         foreground=c["text"],
                         focuscolor=c["panel"],
                         font=("Segoe UI", 10))
    self.style.map("TCheckbutton",
                   background=[("active", c["panel"])],
                   indicatorcolor=[("selected", c["accent"]), ("!selected", c["order_bg"])])
    
    # Spinbox style - matching entries
    self.style.configure("TSpinbox",
                         fieldbackground=c["order_bg"],
                         foreground=c["text"],
                         arrowcolor=c["accent"],
                         borderwidth=0,
                         lightcolor=c["order_bg"],
                         darkcolor=c["order_bg"],
                         padding=8)
    self.style.map("TSpinbox",
                   arrowcolor=[("active", c["accent2"])])
    
    # Notebook styles - clean tabs
    self.style.configure("TNotebook",
                         background=c["panel2"],
                         borderwidth=0,
                         tabmargins=[0, 0, 0, 0])
    self.style.configure("TNotebook.Tab",
                         background=c["panel2"],
                         foreground=c["muted"],
                         padding=(24, 12),
                         borderwidth=0,
                         font=("Segoe UI Semibold", 10))
    self.style.map("TNotebook.Tab",
                   background=[("selected", c["panel"])],
                   foreground=[("selected", c["accent"])],
                   expand=[("selected", [0, 0, 0, 2])])  # Slight raise effect
    
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

  def _build_ui(self, root: Tk) -> None:
    pad = {"padx": 16, "pady": 12}  # Increased padding for more breathing room

    # Main container - let ttkbootstrap handle styling
    import tkinter as tk
    frm = ttk.Frame(root)
    frm.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frm.columnconfigure(1, weight=1)

    row = 0
    # Colored header bar with accent strip
    self._header = tk.Frame(frm, bg=self._colors["bg"], bd=0, highlightthickness=0)
    self._header.grid(row=row, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 8))
    self._header.columnconfigure(0, weight=1)
    
    # Accent strip at top - gradient-like effect
    accent_strip = tk.Frame(self._header, bg=self._colors["accent"], height=5)
    accent_strip.grid(row=0, column=0, columnspan=3, sticky="ew")
    
    self._header_title = tk.Label(
      self._header,
      text="💿 Discogs Auto-Sort",
      bg=self._colors["bg"],
      fg=self._colors["text"],
      font=("Segoe UI Semibold", 22),
      padx=20,
      pady=14,
    )
    self._header_title.grid(row=1, column=0, sticky="w")
    self._header_subtitle = tk.Label(
      self._header,
      text="Vinyl Collection Manager  •  Live Updates  •  Export & Print",
      bg=self._colors["bg"],
      fg=self._colors["muted"],
      font=("Segoe UI", 11),
      padx=20,
      pady=0,
    )
    self._header_subtitle.grid(row=2, column=0, sticky="w", pady=(0, 8))

    # Dark/Light mode toggle button - styled with rounded feel
    self.theme_btn = tk.Button(
      self._header,
      text="🌙 Dark",
      bg=self._colors["accent"],
      fg="#ffffff",
      font=("Segoe UI Semibold", 10),
      bd=0,
      relief="flat",
      padx=14,
      pady=8,
      cursor="hand2",
      activebackground=self._colors["button_hover"],
      activeforeground="#ffffff",
      command=self._toggle_theme,
    )
    self.theme_btn.grid(row=1, column=1, rowspan=2, sticky="e", padx=16, pady=8)
    row += 1

    # Settings card
    settings = ttk.LabelFrame(frm, text="⚙️ Settings")
    settings.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
    settings.columnconfigure(1, weight=1)
    srow = 0

    ttk.Label(settings, text="Token").grid(row=srow, column=0, sticky="w", **pad)
    self.token_entry = ttk.Entry(settings, textvariable=self.v_token, width=44, show="•")
    self.token_entry.grid(row=srow, column=1, sticky="ew", **pad)
    ttk.Checkbutton(settings, text="Show", variable=self.v_show_token, command=self._toggle_token_visibility).grid(row=srow, column=2, sticky="w", **pad)
    srow += 1

    ttk.Label(settings, text="User-Agent").grid(row=srow, column=0, sticky="w", **pad)
    ttk.Entry(settings, textvariable=self.v_user_agent, width=44).grid(row=srow, column=1, sticky="ew", **pad)
    srow += 1

    out_row = ttk.Frame(settings)
    out_row.grid(row=srow, column=0, columnspan=3, sticky="ew", **pad)
    out_row.columnconfigure(1, weight=1)
    ttk.Label(out_row, text="Output Dir").grid(row=0, column=0, sticky="w")
    self._output_entry = ttk.Entry(out_row, textvariable=self.v_output_dir)
    self._output_entry.grid(row=0, column=1, sticky="ew", padx=4)
    # Use bootstyle for rounded buttons
    if TTKBOOTSTRAP_AVAILABLE:
      self._browse_btn = ttk.Button(out_row, text="Browse", bootstyle="info-outline", command=self._choose_dir)
      self._browse_btn.grid(row=0, column=2, sticky="e")
      self._open_btn = ttk.Button(out_row, text="Open", bootstyle="secondary-outline", command=self._open_output_dir)
      self._open_btn.grid(row=0, column=3, sticky="e", padx=(6, 0))
    else:
      self._browse_btn = ttk.Button(out_row, text="Browse", command=self._choose_dir)
      self._browse_btn.grid(row=0, column=2, sticky="e")
      self._open_btn = ttk.Button(out_row, text="Open", command=self._open_output_dir)
      self._open_btn.grid(row=0, column=3, sticky="e", padx=(6, 0))
    srow += 1

    opt = ttk.Frame(settings)
    opt.grid(row=srow, column=0, columnspan=3, sticky="ew", **pad)
    ttk.Label(opt, text="Poll seconds").grid(row=0, column=0, sticky="w")
    self._poll_spin = ttk.Spinbox(opt, from_=15, to=3600, textvariable=self.v_poll, width=8)
    self._poll_spin.grid(row=0, column=1, padx=6)
    self._json_check = ttk.Checkbutton(opt, text="Also JSON", variable=self.v_json)
    self._json_check.grid(row=0, column=2, padx=6, sticky="w")
    self._prices_check = ttk.Checkbutton(opt, text="Show Prices", variable=self.v_show_prices)
    self._prices_check.grid(row=0, column=3, padx=6, sticky="w")
    ttk.Label(opt, text="Currency").grid(row=0, column=4, sticky="w", padx=(6, 0))
    self._currency_combo = ttk.Combobox(opt, textvariable=self.v_currency, values=["USD", "EUR", "GBP", "SEK", "CAD", "AUD", "JPY"], width=5, state="readonly")
    self._currency_combo.grid(row=0, column=5, padx=6)
    # Refresh prices button
    if TTKBOOTSTRAP_AVAILABLE:
      self._refresh_prices_btn = ttk.Button(opt, text="🔄 Refresh Prices", bootstyle="warning-outline", command=self._refresh_prices)
    else:
      self._refresh_prices_btn = ttk.Button(opt, text="🔄 Refresh Prices", command=self._refresh_prices)
    self._refresh_prices_btn.grid(row=0, column=6, padx=6, sticky="w")
    srow += 1

    # Sort options row
    sort_row = ttk.Frame(settings)
    sort_row.grid(row=srow, column=0, columnspan=3, sticky="ew", **pad)
    ttk.Label(sort_row, text="📊 Sort By").grid(row=0, column=0, sticky="w")
    sort_options = [
      ("Artist A-Z", "artist"),
      ("Title A-Z", "title"),
      ("Year", "year"),
      ("Price ↑ Low-High", "price_asc"),
      ("Price ↓ High-Low", "price_desc"),
    ]
    self._sort_combo = ttk.Combobox(
      sort_row, 
      textvariable=self.v_sort_by, 
      values=[opt[1] for opt in sort_options],
      width=15, 
      state="readonly"
    )
    self._sort_combo.grid(row=0, column=1, padx=6, sticky="w")
    # Display friendly names but store values
    ttk.Label(sort_row, text="(Price sorting requires 'Show Prices' enabled)", foreground=self._colors["muted"]).grid(row=0, column=2, sticky="w", padx=6)
    srow += 1

    # Price info note
    price_info = ttk.Frame(settings)
    price_info.grid(row=srow, column=0, columnspan=3, sticky="ew", **pad)
    ttk.Label(price_info, text="ℹ️ Prices shown are the lowest currently listed for your specific pressing, not all versions.", foreground=self._colors["muted"]).grid(row=0, column=0, sticky="w")
    srow += 1

    row += 1

    # Search row with styled entry
    search_row = ttk.Frame(frm)
    search_row.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
    search_row.columnconfigure(1, weight=1)
    ttk.Label(search_row, text="🔍 Search").grid(row=0, column=0, sticky="w")
    self._search_entry = ttk.Entry(search_row, textvariable=self.v_search)
    self._search_entry.grid(row=0, column=1, sticky="ew", padx=6)
    # Use bootstyle for ttkbootstrap rounded buttons
    if TTKBOOTSTRAP_AVAILABLE:
      self._clear_btn = ttk.Button(search_row, text="✕ Clear", bootstyle="secondary-outline", command=lambda: self.v_search.set(""))
      self._clear_btn.grid(row=0, column=2, sticky="e")
    else:
      self._clear_btn = ttk.Button(search_row, text="✕ Clear", style="Secondary.TButton", command=lambda: self.v_search.set(""))
      self._clear_btn.grid(row=0, column=2, sticky="e")
    ttk.Label(search_row, textvariable=self.v_match).grid(row=0, column=3, sticky="e", padx=6)
    self.v_search.trace_add("write", lambda *_: self._on_search_change())
    row += 1

    # Action buttons row with styled buttons - better spacing
    btn = ttk.Frame(frm)
    btn.grid(row=row, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 16))
    btn.columnconfigure(0, weight=1)
    btn.columnconfigure(1, weight=1)
    btn.columnconfigure(2, weight=1)
    btn.columnconfigure(3, weight=1)
    
    # Use ttkbootstrap bootstyle for rounded corners, or fall back to custom styles
    if TTKBOOTSTRAP_AVAILABLE:
      self._refresh_btn = ttk.Button(btn, text="🔄  Refresh", bootstyle="primary", command=self._refresh_now)
      self._refresh_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=6)
      self._export_btn = ttk.Button(btn, text="📁  Export", bootstyle="success", command=self._export_files)
      self._export_btn.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=6)
      self._print_btn = ttk.Button(btn, text="🖨️  Print", bootstyle="secondary", command=self._print_current)
      self._print_btn.grid(row=0, column=2, sticky="ew", padx=(0, 10), pady=6)
      self._stop_btn = ttk.Button(btn, text="⏹️  Stop", bootstyle="danger", command=self._stop_app)
      self._stop_btn.grid(row=0, column=3, sticky="ew", pady=6)
    else:
      self._refresh_btn = ttk.Button(btn, text="🔄  Refresh", style="Primary.TButton", command=self._refresh_now)
      self._refresh_btn.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=6)
      self._export_btn = ttk.Button(btn, text="📁  Export", style="Success.TButton", command=self._export_files)
      self._export_btn.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=6)
      self._print_btn = ttk.Button(btn, text="🖨️  Print", style="Secondary.TButton", command=self._print_current)
      self._print_btn.grid(row=0, column=2, sticky="ew", padx=(0, 10), pady=6)
      self._stop_btn = ttk.Button(btn, text="⏹️  Stop", style="Danger.TButton", command=self._stop_app)
      self._stop_btn.grid(row=0, column=3, sticky="ew", pady=6)
    row += 1

    nb = ttk.Notebook(frm)
    nb.grid(row=row, column=0, columnspan=2, sticky="nsew", **pad)
    frm.rowconfigure(row, weight=1)

    order_fr = ttk.Frame(nb)
    nb.add(order_fr, text="📋 Shelf Order")
    order_fr.rowconfigure(0, weight=1)
    order_fr.columnconfigure(0, weight=1)

    order_wrap = ttk.Frame(order_fr)
    order_wrap.grid(row=0, column=0, sticky="nsew")
    order_wrap.rowconfigure(0, weight=1)
    order_wrap.columnconfigure(0, weight=1)

    order_scroll = ttk.Scrollbar(order_wrap, orient="vertical")
    order_scroll.grid(row=0, column=1, sticky="ns")

    self.order_text = tk.Text(
      order_wrap,
      height=18,
      width=90,
      wrap="none",
      yscrollcommand=order_scroll.set,
      font=("Cascadia Code", 11),
      background=self._colors["order_bg"],
      foreground=self._colors["order_fg"],
      relief="flat",
      bd=0,
      padx=12,
      pady=12,
      insertbackground=self._colors["accent"],
      selectbackground=self._colors["accent"],
      selectforeground="#ffffff",
    )
    self.order_text.grid(row=0, column=0, sticky="nsew")
    order_scroll.config(command=self.order_text.yview)
    
    # Configure text tags for styled output
    self.order_text.tag_configure("search_match", background="#fbbf24", foreground="#1a1a2e")
    self.order_text.tag_configure("row_even", background=self._colors["order_bg"])
    self.order_text.tag_configure("row_odd", background="#1a2d4d" if self.v_dark_mode.get() else "#f0f4f8")
    self.order_text.tag_configure("artist", foreground=self._colors["accent"], font=("Cascadia Code", 11, "bold"))
    self.order_text.tag_configure("title", foreground=self._colors["order_fg"], font=("Cascadia Code", 11))
    self.order_text.tag_configure("year", foreground=self._colors["muted"], font=("Cascadia Code", 10))
    self.order_text.tag_configure("label", foreground="#8892b0", font=("Cascadia Code", 10))
    self.order_text.tag_configure("price", foreground=self._colors["success"], font=("Cascadia Code", 10, "bold"))
    self.order_text.tag_configure("price_none", foreground=self._colors["muted"], font=("Cascadia Code", 10))
    self.order_text.tag_configure("row_number", foreground="#4a5568", font=("Cascadia Code", 9))

    log_fr = ttk.Frame(nb)
    nb.add(log_fr, text="📜 Log")
    log_fr.rowconfigure(0, weight=1)
    log_fr.columnconfigure(0, weight=1)
    log_wrap = ttk.Frame(log_fr)
    log_wrap.grid(row=0, column=0, sticky="nsew")
    log_wrap.rowconfigure(0, weight=1)
    log_wrap.columnconfigure(0, weight=1)
    log_scroll = ttk.Scrollbar(log_wrap, orient="vertical")
    log_scroll.grid(row=0, column=1, sticky="ns")
    self.log = tk.Text(
      log_wrap,
      height=18,
      width=90,
      yscrollcommand=log_scroll.set,
      font=("Cascadia Code", 10),
      background=self._colors["panel2"],
      foreground=self._colors["text"],
      insertbackground=self._colors["text"],
      relief="flat",
      bd=0,
      padx=12,
      pady=12,
      selectbackground=self._colors["accent"],
      selectforeground="#ffffff",
    )
    self.log.grid(row=0, column=0, sticky="nsew")
    log_scroll.config(command=self.log.yview)

    # Status bar with accent background - clean footer with multiple info sections
    self._status_bar = tk.Frame(frm, bg=self._colors["accent"], bd=0, highlightthickness=0)
    self._status_bar.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=0, pady=(12, 0))
    self._status_bar.columnconfigure(0, weight=1)
    
    # Left section - main status
    self._status_label = tk.Label(
      self._status_bar, 
      textvariable=self.v_status, 
      bg=self._colors["accent"], 
      fg="#ffffff", 
      anchor="w", 
      padx=20, 
      pady=10,
      font=("Segoe UI Semibold", 10)
    )
    self._status_label.grid(row=0, column=0, sticky="w")
    
    # Right section - info items
    info_frame = tk.Frame(self._status_bar, bg=self._colors["accent"])
    info_frame.grid(row=0, column=1, sticky="e", padx=10)
    
    # Collection count
    self._count_icon = tk.Label(info_frame, text="💿", bg=self._colors["accent"], fg="#ffffff", font=("Segoe UI", 10))
    self._count_icon.grid(row=0, column=0, padx=(0, 4))
    self._count_label = tk.Label(info_frame, textvariable=self.v_collection_count, bg=self._colors["accent"], fg="#ffffff", font=("Segoe UI", 10))
    self._count_label.grid(row=0, column=1, padx=(0, 16))
    
    # Separator
    tk.Label(info_frame, text="•", bg=self._colors["accent"], fg="#a0a0ff", font=("Segoe UI", 10)).grid(row=0, column=2, padx=(0, 16))
    
    # Last sync time
    self._sync_icon = tk.Label(info_frame, text="🕓", bg=self._colors["accent"], fg="#ffffff", font=("Segoe UI", 10))
    self._sync_icon.grid(row=0, column=3, padx=(0, 4))
    self._sync_label = tk.Label(info_frame, textvariable=self.v_last_sync, bg=self._colors["accent"], fg="#ffffff", font=("Segoe UI", 10))
    self._sync_label.grid(row=0, column=4, padx=(0, 16))
    
    # Separator
    self._value_sep = tk.Label(info_frame, text="•", bg=self._colors["accent"], fg="#a0a0ff", font=("Segoe UI", 10))
    self._value_sep.grid(row=0, column=5, padx=(0, 16))
    self._value_sep.grid_remove()  # Hidden by default
    
    # Total value (shown only when prices enabled)
    self._value_icon = tk.Label(info_frame, text="💰", bg=self._colors["accent"], fg="#ffffff", font=("Segoe UI", 10))
    self._value_icon.grid(row=0, column=6, padx=(0, 4))
    self._value_icon.grid_remove()  # Hidden by default
    self._value_label = tk.Label(info_frame, textvariable=self.v_total_value, bg=self._colors["accent"], fg="#ffffff", font=("Segoe UI Semibold", 10))
    self._value_label.grid(row=0, column=7, padx=(0, 10))
    self._value_label.grid_remove()  # Hidden by default
    
    # Set up tooltips
    self._setup_tooltips()

  def _choose_dir(self) -> None:
    directory = filedialog.askdirectory(initialdir=self.v_output_dir.get() or str(Path.cwd()))
    if directory:
      self.v_output_dir.set(directory)

  def _setup_tooltips(self) -> None:
    """Set up tooltips for all interactive widgets."""
    # Settings tooltips
    ToolTip(self.token_entry, "Your Discogs personal access token.\nGet one at discogs.com/settings/developers")
    ToolTip(self._output_entry, "Directory where sorted lists will be saved (TXT, CSV, JSON)")
    ToolTip(self._browse_btn, "Browse for an output folder")
    ToolTip(self._open_btn, "Open the output folder in File Explorer")
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

  def _setup_keyboard_shortcuts(self) -> None:
    """Set up keyboard shortcuts for common actions."""
    # Ctrl+F - Focus search
    self.root.bind("<Control-f>", lambda e: self._focus_search())
    self.root.bind("<Control-F>", lambda e: self._focus_search())
    
    # Escape - Clear search (when search has focus)
    self._search_entry.bind("<Escape>", lambda e: self._clear_search())
    
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
  
  def _focus_search(self) -> None:
    """Focus the search entry field."""
    self._search_entry.focus_set()
    self._search_entry.select_range(0, "end")
  
  def _clear_search(self) -> None:
    """Clear the search field."""
    self.v_search.set("")
    self._search_entry.focus_set()

  def _refresh_prices(self) -> None:
    """Clear cached prices and trigger a refresh with price fetching enabled."""
    currency = self.v_currency.get().strip() or "USD"
    cleared = self._collection_cache.clear_prices(currency)
    self._log(f"Cleared {cleared} cached prices for {currency}.")
    
    # Enable show prices and trigger refresh
    self.v_show_prices.set(True)
    self._refresh_now()

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
      }
      save_config(config)
    except Exception:
      pass

  def _open_output_dir(self) -> None:
    path = self.v_output_dir.get().strip() or str(Path.cwd())
    try:
      subprocess.run(["open", path], check=False)
    except Exception:
      pass

  def _toggle_token_visibility(self) -> None:
    try:
      self.token_entry.configure(show="" if self.v_show_token.get() else "•")
    except Exception:
      pass

  def _toggle_theme(self) -> None:
    """Toggle between dark and light mode."""
    self.v_dark_mode.set(not self.v_dark_mode.get())
    self._apply_theme()

  def _apply_theme(self) -> None:
    """Apply the current theme colors to all widgets."""
    if self.v_dark_mode.get():
      self._colors = self._dark_colors.copy()
      self.theme_btn.config(text="🌙 Dark")
      # Switch ttkbootstrap theme if available
      if TTKBOOTSTRAP_AVAILABLE:
        self.style.theme_use("darkly")
    else:
      self._colors = self._light_colors.copy()
      self.theme_btn.config(text="☀️ Light")
      # Switch ttkbootstrap theme if available
      if TTKBOOTSTRAP_AVAILABLE:
        self.style.theme_use("litera")

    # Reconfigure all ttk styles
    self._configure_styles()

    # Update theme button
    self.theme_btn.config(
      bg=self._colors["accent"],
      fg="#ffffff",
      activebackground=self._colors["button_hover"],
      activeforeground="#ffffff"
    )

    # Update header
    try:
      self._header.config(bg=self._colors["bg"])
      self._header_title.config(bg=self._colors["bg"], fg=self._colors["text"])
      self._header_subtitle.config(bg=self._colors["bg"], fg=self._colors["muted"])
      # Update accent strip if it exists
      for child in self._header.winfo_children():
        if child.winfo_class() == "Frame" and child.cget("height") == 4:
          child.config(bg=self._colors["accent"])
    except Exception:
      pass

    # Update status bar
    try:
      self._status_bar.config(bg=self._colors["accent"])
      self._status_label.config(bg=self._colors["accent"], fg="#ffffff")
      # Update all status bar children
      for widget in [self._count_icon, self._count_label, self._sync_icon, self._sync_label, 
                     self._value_sep, self._value_icon, self._value_label]:
        try:
          widget.config(bg=self._colors["accent"])
        except Exception:
          pass
      # Update info frame background
      for child in self._status_bar.winfo_children():
        try:
          child.config(bg=self._colors["accent"])
        except Exception:
          pass
    except Exception:
      pass

    # Update order text widget
    try:
      self.order_text.config(
        background=self._colors["order_bg"],
        foreground=self._colors["order_fg"],
        insertbackground=self._colors["order_fg"],
      )
      # Update all text tags for current theme
      if self.v_dark_mode.get():
        self.order_text.tag_configure("search_match", background="#fbbf24", foreground="#1a1a2e")
        self.order_text.tag_configure("row_even", background=self._colors["order_bg"])
        self.order_text.tag_configure("row_odd", background="#1a2d4d")
        self.order_text.tag_configure("artist", foreground=self._colors["accent"])
        self.order_text.tag_configure("title", foreground=self._colors["order_fg"])
        self.order_text.tag_configure("price", foreground=self._colors["success"])
      else:
        self.order_text.tag_configure("search_match", background="#fef08a", foreground="#1a1a2e")
        self.order_text.tag_configure("row_even", background=self._colors["order_bg"])
        self.order_text.tag_configure("row_odd", background="#e8eef4")
        self.order_text.tag_configure("artist", foreground=self._colors["accent"])
        self.order_text.tag_configure("title", foreground=self._colors["order_fg"])
        self.order_text.tag_configure("price", foreground=self._colors["success"])
      
      # Re-render if we have results
      if self._last_result:
        self._render_order(self._last_result)
    except Exception:
      pass

    # Update log widget
    try:
      self.log.config(
        background=self._colors["order_bg"],
        foreground=self._colors["order_fg"],
        insertbackground=self._colors["order_fg"],
      )
    except Exception:
      pass

    # Update root window background
    try:
      self.root.config(bg=self._colors["panel2"])
    except Exception:
      pass

  def _log(self, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    self.log_q.put(f"[{ts}] {msg}\n")

  def _pump_queues(self) -> None:
    try:
      while True:
        line = self.log_q.get_nowait()
        self.log.insert("end", line)
        self.log.see("end")
    except queue.Empty:
      pass

    try:
      while True:
        result = self.result_q.get_nowait()
        self._last_result = result
        self._render_order(result)
        self._update_status_bar(result)
    except queue.Empty:
      pass
    
    # Handle progress dialog commands from background thread
    try:
      while True:
        action, message = self.progress_q.get_nowait()
        if action == "show":
          if self._progress_dialog is None:
            self._progress_dialog = ProgressDialog(self.root, "Fetching Data", message or "Please wait...")
        elif action == "update":
          if self._progress_dialog is not None:
            self._progress_dialog.update_progress(message or "")
        elif action == "message":
          if self._progress_dialog is not None:
            self._progress_dialog.update_message(message or "")
        elif action == "close":
          if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog = None
    except queue.Empty:
      pass

    self.root.after(100, self._pump_queues)

  def _render_order(self, result: BuildResult) -> None:
    self.order_text.delete("1.0", "end")
    if not result.lines:
      self.order_text.insert("end", "(No matching LPs found.)\n")
      self.v_match.set("")
      return

    # Render with styled formatting for better readability
    for i, line in enumerate(result.lines):
      row_tag = "row_odd" if i % 2 == 1 else "row_even"
      row_num = f"{i+1:3d}. "
      
      # Parse the line to colorize parts
      # Format: "Artist — Title (Year) [Label Catno] - Price"
      self.order_text.insert("end", row_num, ("row_number", row_tag))
      
      # Try to parse and style different parts
      if " — " in line:
        parts = line.split(" — ", 1)
        artist = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        
        self.order_text.insert("end", artist, ("artist", row_tag))
        self.order_text.insert("end", " — ", ("title", row_tag))
        
        # Check for price part at end
        if " - " in rest and ("SEK" in rest or "USD" in rest or "EUR" in rest or "[Not listed]" in rest):
          # Split off price
          price_idx = rest.rfind(" - ")
          title_part = rest[:price_idx]
          price_part = rest[price_idx:]
          
          # Check for year in parentheses
          if "(" in title_part and ")" in title_part:
            # Find year portion
            year_start = title_part.rfind("(")
            title_only = title_part[:year_start].rstrip()
            year_and_label = title_part[year_start:]
            
            self.order_text.insert("end", title_only, ("title", row_tag))
            self.order_text.insert("end", " " + year_and_label, ("label", row_tag))
          else:
            self.order_text.insert("end", title_part, ("title", row_tag))
          
          # Style price
          if "[Not listed]" in price_part:
            self.order_text.insert("end", price_part, ("price_none", row_tag))
          else:
            self.order_text.insert("end", price_part, ("price", row_tag))
        else:
          self.order_text.insert("end", rest, ("title", row_tag))
      else:
        # Fallback - just insert the line
        self.order_text.insert("end", line, ("title", row_tag))
      
      self.order_text.insert("end", "\n", row_tag)
    
    self.order_text.see("1.0")
    self._highlight_search()

  def _update_status_bar(self, result: BuildResult) -> None:
    """Update the status bar with collection info."""
    from datetime import datetime
    
    # Update collection count
    count = len(result.rows_sorted)
    self.v_collection_count.set(f"{count} albums")
    
    # Update last sync time
    now = datetime.now()
    self.v_last_sync.set(f"Synced {now.strftime('%H:%M')}")
    
    # Calculate and show total value if prices are available
    if self.v_show_prices.get() and result.rows_sorted:
      total_value = 0.0
      priced_count = 0
      currency = ""
      
      for row in result.rows_sorted:
        if row.lowest_price is not None:
          total_value += row.lowest_price
          priced_count += 1
          if not currency and row.price_currency:
            currency = row.price_currency
      
      if priced_count > 0:
        # Format the value nicely
        if total_value >= 1000:
          value_str = f"{total_value:,.0f} {currency}"
        else:
          value_str = f"{total_value:.0f} {currency}"
        
        self.v_total_value.set(f"~{value_str} ({priced_count} priced)")
        
        # Show the value section
        self._value_sep.grid()
        self._value_icon.grid()
        self._value_label.grid()
      else:
        # Hide value section if no prices
        self._value_sep.grid_remove()
        self._value_icon.grid_remove()
        self._value_label.grid_remove()
    else:
      # Hide value section
      self._value_sep.grid_remove()
      self._value_icon.grid_remove()
      self._value_label.grid_remove()

  def _highlight_search(self) -> None:
    # Highlight matches within the displayed text without filtering out lines.
    self.order_text.tag_remove("search_match", "1.0", "end")
    q = (self.v_search.get() or "").strip()
    if not q:
      if self._last_result is not None:
        self.v_match.set(f"{len(self._last_result.lines)} items")
      else:
        self.v_match.set("")
      return

    start = "1.0"
    matches = 0
    first_match: str | None = None
    while True:
      idx = self.order_text.search(q, start, stopindex="end", nocase=True)
      if not idx:
        break
      if first_match is None:
        first_match = idx
      end = f"{idx}+{len(q)}c"
      self.order_text.tag_add("search_match", idx, end)
      matches += 1
      start = end

    self.v_match.set(f"{matches} matches" if matches != 1 else "1 match")
    if first_match is not None:
      self.order_text.see(first_match)
      try:
        self.order_text.mark_set("insert", first_match)
      except Exception:
        pass

  def _on_search_change(self) -> None:
    self._highlight_search()

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
    )

  def _refresh_now(self) -> None:
    # Wake the watcher and force immediate check
    self._log("Manual refresh requested.")
    self.v_status.set("Refresh requested…")
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

    txt_path = out_dir / "vinyl_shelf_order.txt"
    csv_path = out_dir / "vinyl_shelf_order.csv"
    core.write_txt(result.rows_sorted, txt_path, dividers=False, align=False, show_country=False)
    core.write_csv(result.rows_sorted, csv_path)
    self._log(f"Exported: {txt_path.name}")
    self._log(f"Exported: {csv_path.name}")

    if cfg.write_json:
      json_path = out_dir / "vinyl_shelf_order.json"
      core.write_json(result.rows_sorted, json_path)
      self._log(f"Exported: {json_path.name}")

    messagebox.showinfo("Export", f"Wrote files to:\n{out_dir}")
    self.v_status.set(f"Exported to: {out_dir}")

  def _print_current(self) -> None:
    result = self._last_result
    if not result or not result.lines:
      messagebox.showinfo("Print", "Nothing to print yet. Wait for the first build.")
      return

    if not messagebox.askyesno("Print", "Send the current shelf order to your default printer?"):
      return

    if subprocess.run(["sh", "-lc", "command -v lpr"], capture_output=True).returncode != 0:
      messagebox.showerror("Print", "Could not find 'lpr' command on this system.")
      return

    try:
      with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(result.lines) + "\n")
        tmp_path = f.name
      subprocess.run(["lpr", tmp_path], check=True)
      self._log("Sent to printer via lpr.")
      self.v_status.set("Sent to printer.")
    except Exception as e:
      messagebox.showerror("Print", f"Printing failed: {e}")
      self.v_status.set("Print failed.")

  def _watch_loop(self) -> None:
    """Background thread: poll collection count; rebuild on change or manual refresh."""
    self._log("Watcher started.")
    self.v_status.set("Watching for changes…")
    
    # Progress callback to send messages to the main thread via queue
    def progress_callback(action: str, message: str | None):
      self.progress_q.put((action, message))
    
    while not self._stop.is_set():
      cfg = self._get_cfg()
      try:
        # Check for token
        token_str = cfg.token or os.environ.get("DISCOGS_TOKEN", "")
        if not token_str:
          self._log("Error: No Discogs token provided. Enter your token in the Settings.")
          self.v_status.set("Error: No token (see Log tab)")
          self._wake.clear()
          self._wake.wait(timeout=cfg.poll_seconds)
          continue

        token = core.get_token(cfg.token or None)
        headers = core.discogs_headers(token, cfg.user_agent)
        ident = core.get_identity(headers)
        username = ident.get("username")
        if not username:
          raise RuntimeError("Could not determine username from token.")

        count = get_collection_count(headers, username)
        force = self._force_rebuild
        self._force_rebuild = False

        if self._last_count is None or force:
          if self._last_count is None:
            self._last_count = count
            self._log(f"Initial collection count: {count}")
          else:
            self._log(f"Forced refresh. Collection count: {count}")
          # Build once on startup or forced refresh
          self._log("Building shelf order…")
          self.v_status.set("Building…")
          result = build_once(cfg, self._log, progress_callback, self._collection_cache)
          self.result_q.put(result)
          self._last_built_at = time.time()
          self._log(f"Build complete. Items: {len(result.rows_sorted)}")
          self.v_status.set(f"Built {len(result.rows_sorted)} items. Polling every {cfg.poll_seconds}s")
        else:
          if count != self._last_count:
            self._log(f"Collection changed: {self._last_count} → {count}")
            self._last_count = count
            self._log("Rebuilding shelf order…")
            self.v_status.set("Rebuilding…")
            result = build_once(cfg, self._log, progress_callback, self._collection_cache)
            self.result_q.put(result)
            self._last_built_at = time.time()
            self._log(f"Build complete. Items: {len(result.rows_sorted)}")
            self.v_status.set(f"Built {len(result.rows_sorted)} items. Polling every {cfg.poll_seconds}s")
          else:
            self.v_status.set(f"No changes. Polling every {cfg.poll_seconds}s")

      except Exception as e:
        self._log(f"Error: {e}")
        self._log(traceback.format_exc())
        self.v_status.set("Error (see Log tab).")
        # Close any open progress dialog on error
        self.progress_q.put(("close", None))

      # Wait for next poll or manual refresh
      self._wake.clear()
      self._wake.wait(timeout=cfg.poll_seconds)

    self._log("Watcher stopped.")


def main() -> None:
  # Use ttkbootstrap Window for better theming if available
  if TTKBOOTSTRAP_AVAILABLE:
    import ttkbootstrap as ttk_bs
    root = ttk_bs.Window(themename="darkly")
  else:
    root = Tk()
  
  try:
    root.call("tk", "scaling", 1.2)
  except Exception:
    pass
  # Start maximized (fullscreen window)
  root.state('zoomed')
  App(root)
  root.mainloop()


if __name__ == "__main__":
  main()
