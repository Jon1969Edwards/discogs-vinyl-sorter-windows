#!/usr/bin/env python3
"""Discogs Auto-Sort GUI

A modularized GUI version. Album info popup logic is now in gui/album_popup.py.

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

# PIL ImageTk import for type hints and runtime use
try:
  from gui.album_popup import AlbumPopup
  from gui.wishlist_tab import WishlistTab
except ImportError:
  ImageTk = None

# Use ttkbootstrap for modern rounded widgets
try:
  import ttkbootstrap as ttk
  TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
  from tkinter import ttk
  TTKBOOTSTRAP_AVAILABLE = False

from tkinter import Tk, StringVar, BooleanVar, IntVar, filedialog, messagebox
import tkinter as tk

import discogs_app as core
from core.models import ReleaseRow, BuildResult

# Modularized popup
from gui.album_popup import AlbumPopup


POLL_SECONDS_DEFAULT = 300  # 5 minutes
CONFIG_FILE = Path(__file__).parent / ".discogs_config.json"
# Simple key for obfuscation (not meant to be cryptographically secure, just prevents casual viewing)
_OBFUSCATE_KEY = b"DiscogsVinylSorter2026"

# UI font constants (avoid duplicated literals for linters and consistency)
FONT_SEGOE_UI = "Segoe UI"
FONT_SEGOE_UI_SEMIBOLD = "Segoe UI Semibold"

# Button style constants
SECONDARY_TBUTTON_STYLE = "Secondary.TButton"


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


# Manual order persistence file
MANUAL_ORDER_FILE = Path(__file__).parent / ".discogs_manual_order.json"


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


# Thumbnail cache directory
THUMBNAIL_CACHE_DIR = Path(__file__).parent / ".discogs_thumbnails"


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from PIL import ImageTk

class ThumbnailCache:
  """Cache for album artwork thumbnails."""
  
  THUMB_SIZE = (40, 40)  # Size for display in Treeview
  PREVIEW_SIZE = (200, 200)  # Size for hover preview
  
  def __init__(self):
    """Initialize thumbnail cache."""
    self.cache_dir = THUMBNAIL_CACHE_DIR
    self.cache_dir.mkdir(exist_ok=True)
    from typing import Optional
    from typing import Dict
    self._photo_cache: Dict[int, "ImageTk.PhotoImage"] = {}  # type: ignore # In-memory cache of PhotoImage objects
    self._preview_cache: Dict[int, "ImageTk.PhotoImage"] = {}  # type: ignore # Cache for larger preview images
    self._placeholder: Optional["ImageTk.PhotoImage"] = None # type: ignore
    self._pil_available = False
    self._check_pil()
  
  def _check_pil(self) -> None:
    """Check if PIL/Pillow is available."""
    try:
      from PIL import Image, ImageTk
      self._pil_available = True
    except ImportError:
      self._pil_available = False
  
  def is_available(self) -> bool:
    """Check if thumbnail support is available (PIL installed)."""
    return self._pil_available
  
  def _get_cache_path(self, release_id: int, preview: bool = False) -> Path:
    """Get the cache file path for a release."""
    suffix = "_preview" if preview else ""
    return self.cache_dir / f"{release_id}{suffix}.png"
  
  def has_cached(self, release_id: int) -> bool:
    """Check if we have a cached thumbnail for this release."""
    return self._get_cache_path(release_id).exists()
  
  def get_photo(self, release_id: int) -> "ImageTk.PhotoImage | None": # type: ignore
    """Get a PhotoImage for a release (from memory cache)."""
    return self._photo_cache.get(release_id)
  
  def get_placeholder(self) -> "ImageTk.PhotoImage | None": # type: ignore
    """Get a placeholder image for releases without artwork."""
    if not self._pil_available:
      return None
    
    if self._placeholder is not None:
      return self._placeholder
    
    try:
      from PIL import Image, ImageTk, ImageDraw
      
      # Create a simple placeholder (gray square with vinyl icon)
      img = Image.new("RGBA", self.THUMB_SIZE, (60, 60, 80, 255))
      draw = ImageDraw.Draw(img)
      
      # Draw a simple vinyl record icon
      cx, cy = self.THUMB_SIZE[0] // 2, self.THUMB_SIZE[1] // 2
      r = min(cx, cy) - 4
      draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(100, 100, 120), width=2)
      draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(100, 100, 120))
      
      self._placeholder = ImageTk.PhotoImage(img)
      return self._placeholder
    except Exception:
      return None
  
  def download_thumbnail(self, release_id: int, thumb_url: str, headers: dict[str, str]) -> bool:
    """Download and cache a thumbnail. Returns True on success."""
    if not self._pil_available or not thumb_url:
      return False
    
    cache_path = self._get_cache_path(release_id)
    if cache_path.exists():
      return True  # Already cached
    
    try:
      import requests
      from PIL import Image
      from io import BytesIO
      
      # Download the image
      resp = requests.get(thumb_url, headers=headers, timeout=10)
      if resp.status_code != 200:
        return False
      
      # Open and resize
      img = Image.open(BytesIO(resp.content))
      img = img.convert("RGBA")
      img.thumbnail(self.THUMB_SIZE, Image.Resampling.LANCZOS)
      
      # Create a square canvas and center the image
      square = Image.new("RGBA", self.THUMB_SIZE, (30, 30, 50, 255))
      offset = ((self.THUMB_SIZE[0] - img.width) // 2, (self.THUMB_SIZE[1] - img.height) // 2)
      square.paste(img, offset)
      
      # Save to cache
      square.save(cache_path, "PNG")
      return True
    except Exception:
      return False
  
  def load_photo(self, release_id: int) -> "ImageTk.PhotoImage | None": # type: ignore
    """Load a cached thumbnail as a PhotoImage."""
    if not self._pil_available:
      return None
    
    # Check memory cache first
    if release_id in self._photo_cache:
      return self._photo_cache[release_id]
    
    cache_path = self._get_cache_path(release_id)
    if not cache_path.exists():
      return None
    
    try:
      from PIL import Image, ImageTk
      
      img = Image.open(cache_path)
      photo = ImageTk.PhotoImage(img)
      self._photo_cache[release_id] = photo
      return photo
    except Exception:
      return None
  
  def clear_memory_cache(self) -> None:
    """Clear the in-memory PhotoImage cache."""
    self._photo_cache.clear()
    self._preview_cache.clear()
    self._placeholder = None
  
  def load_preview(self, release_id: int, cover_url: str = None, headers: dict = None) -> "ImageTk.PhotoImage | None": # type: ignore
    """Load a larger preview image for hover display."""
    if not self._pil_available:
      return None
    
    # Check memory cache first
    if release_id in self._preview_cache:
      return self._preview_cache[release_id]
    
    # Check if preview file exists on disk
    preview_path = self._get_cache_path(release_id, preview=True)
    if preview_path.exists():
      try:
        from PIL import Image, ImageTk
        img = Image.open(preview_path)
        photo = ImageTk.PhotoImage(img)
        self._preview_cache[release_id] = photo
        return photo
      except Exception:
        pass
    
    # If we have a cover_url, download the larger image
    if cover_url and headers:
      try:
        import requests
        from PIL import Image, ImageTk
        from io import BytesIO
        
        resp = requests.get(cover_url, headers=headers, timeout=5)
        if resp.status_code == 200:
          img = Image.open(BytesIO(resp.content))
          img = img.convert("RGBA")
          
          # Resize to preview size while maintaining aspect ratio
          img.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
          
          # Create a square canvas and center the image
          square = Image.new("RGBA", self.PREVIEW_SIZE, (30, 30, 50, 255))
          offset = ((self.PREVIEW_SIZE[0] - img.width) // 2, (self.PREVIEW_SIZE[1] - img.height) // 2)
          square.paste(img, offset)
          
          # Save to cache
          square.save(preview_path, "PNG")
          
          photo = ImageTk.PhotoImage(square)
          self._preview_cache[release_id] = photo
          return photo
      except Exception:
        pass
    
    # Fall back to upscaling the small thumbnail
    small_path = self._get_cache_path(release_id, preview=False)
    if small_path.exists():
      try:
        from PIL import Image, ImageTk
        img = Image.open(small_path)
        img = img.resize(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self._preview_cache[release_id] = photo
        return photo
      except Exception:
        pass
    
    return None


class ImagePreviewPopup:
  """Popup window for showing enlarged album artwork on hover."""
  
  def __init__(self, parent, thumbnail_cache: ThumbnailCache):
    self.parent = parent
    self.cache = thumbnail_cache
    self.popup: tk.Toplevel | None = None
    self.label: tk.Label | None = None
    self.current_release_id: int | None = None
    self._hide_job: str | None = None
  
  def show(self, release_id: int, thumb_url: str, headers: dict, x: int, y: int) -> None:
    """Show the preview popup at the specified position."""
    if not self.cache.is_available():
      return
    
    # Cancel any pending hide
    if self._hide_job:
      self.parent.after_cancel(self._hide_job)
      self._hide_job = None
    
    # If already showing this release, just reposition
    if self.popup and self.current_release_id == release_id:
      self._position_popup(x, y)
      return
    
    # Get the preview image
    photo = self.cache.load_preview(release_id, thumb_url, headers)
    if not photo:
      return
    
    self.current_release_id = release_id
    
    # Create or update the popup window
    if not self.popup:
      self.popup = tk.Toplevel(self.parent)
      self.popup.wm_overrideredirect(True)  # No window decorations
      self.popup.wm_attributes("-topmost", True)
      
      # Create frame with border
      frame = tk.Frame(self.popup, bg="#1a1a2e", bd=2, relief="solid")
      frame.pack(fill="both", expand=True)
      
      self.label = tk.Label(frame, bg="#1a1a2e")
      self.label.pack(padx=2, pady=2)
    
    # Update the image
    self.label.config(image=photo)
    self.label.image = photo  # Keep reference
    
    # Position the popup
    self._position_popup(x, y)
    
    self.popup.deiconify()
  
  def _position_popup(self, x: int, y: int) -> None:
    """Position the popup near the cursor but ensure it stays on screen."""
    if not self.popup:
      return
    
    # Offset from cursor
    offset_x = 20
    offset_y = -100
    
    # Get screen dimensions
    screen_w = self.parent.winfo_screenwidth()
    screen_h = self.parent.winfo_screenheight()
    
    # Calculate position
    popup_w = self.cache.PREVIEW_SIZE[0] + 8
    popup_h = self.cache.PREVIEW_SIZE[1] + 8
    
    pos_x = x + offset_x
    pos_y = y + offset_y
    
    # Keep on screen
    if pos_x + popup_w > screen_w:
      pos_x = x - popup_w - 10
    if pos_y + popup_h > screen_h:
      pos_y = screen_h - popup_h - 10
    if pos_y < 0:
      pos_y = 10
    
    self.popup.wm_geometry(f"+{pos_x}+{pos_y}")
  
  def hide(self, delay: int = 100) -> None:
    """Hide the popup with optional delay."""
    if self._hide_job:
      self.parent.after_cancel(self._hide_job)
    
    def do_hide():
      if self.popup:
        self.popup.withdraw()
      self.current_release_id = None
      self._hide_job = None
    
    if delay > 0:
      self._hide_job = self.parent.after(delay, do_hide)
    else:
      do_hide()
  
  def destroy(self) -> None:
    """Destroy the popup window."""
    if self.popup:
      self.popup.destroy()
      self.popup = None
      self.label = None


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





class ProgressDialog:
  """A modal progress dialog with a spinning vinyl record animation."""

  def set_error(self, message: str) -> None:
    """Show error message with red highlight."""
    self.msg_label.config(text=message, fg="#ff5555")
    self.progress_label.config(text="Error", fg="#ff5555")
    self.top.configure(bg="#2e1620")
    self.title_label.config(fg="#ff5555")
    self.top.update()

  def set_done(self, message: str = "Done!") -> None:
    """Show done message with green highlight, then close after short delay."""
    self.msg_label.config(text=message, fg="#55ff55")
    self.progress_label.config(text="Done", fg="#55ff55")
    self.top.configure(bg="#162e20")
    self.title_label.config(fg="#55ff55")
    self.top.update()
    self.top.after(900, self.close)

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
    
    # Title label at top (dynamic)
    self.title_label = tk.Label(
      self.top,
      text=title,
      font=(FONT_SEGOE_UI_SEMIBOLD, 15),
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
      font=(FONT_SEGOE_UI, 10),
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
      font=(FONT_SEGOE_UI_SEMIBOLD, 12),
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
      font=(FONT_SEGOE_UI_SEMIBOLD, 10),
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
      font=(FONT_SEGOE_UI, 9),
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


def build_once(cfg: AutoConfig, log: callable, progress_callback: callable = None, cache: CollectionCache = None, main_progress_q=None) -> BuildResult:
  """Build the shelf order once, with granular progress updates."""
  if main_progress_q:
    main_progress_q.put(("update", "Fetching collection from Discogs..."))
  try:
    _, headers, username = _get_user_headers(cfg, log)
  except Exception as e:
    if main_progress_q:
      main_progress_q.put(("error", f"Failed to get user headers: {e}"))
    raise
  if cache:
    cache.set_username(username)
  out_dir = Path(cfg.output_dir)
  out_dir.mkdir(parents=True, exist_ok=True)
  if main_progress_q:
    main_progress_q.put(("update", "Collecting rows from Discogs...") )
  try:
    rows = _collect_rows(cfg, headers, username)
  except Exception as e:
    if main_progress_q:
      main_progress_q.put(("error", f"Failed to collect rows: {e}"))
    raise
  if not rows:
    log("No matching LPs found.")
    if main_progress_q:
      main_progress_q.put(("error", "No matching LPs found."))
    return BuildResult(username=username, rows_sorted=[], lines=[])
  need_prices = cfg.show_prices or cfg.sort_by in ("price_asc", "price_desc")
  if main_progress_q:
    main_progress_q.put(("update", "Checking if price data is needed...") )
  if need_prices:
    if main_progress_q:
      main_progress_q.put(("update", "Fetching album prices from Discogs Marketplace...") )
    try:
      _handle_prices(cfg, log, progress_callback, cache, headers, rows, main_progress_q)
    except Exception as e:
      if main_progress_q:
        main_progress_q.put(("error", f"Failed to fetch prices: {e}"))
      raise
  try:
    if main_progress_q:
      main_progress_q.put(("update", "Sorting collection...") )
    rows_sorted = core.sort_rows(rows, "normal", sort_by=cfg.sort_by)
    if main_progress_q:
      main_progress_q.put(("update", "Generating output files...") )
    lines = core.generate_txt_lines(rows_sorted, dividers=False, align=False, show_country=False, show_price=need_prices)
    if main_progress_q:
      main_progress_q.put(("done", "Done!"))
    return BuildResult(username=username, rows_sorted=rows_sorted, lines=lines)
  except Exception as e:
    if main_progress_q:
      main_progress_q.put(("error", f"Build failed: {e}"))
    raise

def _get_user_headers(cfg: AutoConfig, log: callable):
    token = core.get_token(cfg.token or None)
    headers = core.discogs_headers(token, cfg.user_agent)
    ident = core.get_identity(headers)
    username = ident.get("username")
    if not username:
        raise RuntimeError("Could not determine username from token.")
    log(f"User: {username}")
    return token, headers, username

def _collect_rows(cfg: AutoConfig, headers: dict, username: str):
    return core.collect_lp_rows(
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

def _handle_prices(cfg, log, progress_callback, cache, headers, rows, main_progress_q=None):
  releases_needing_fetch, cached_count = _populate_prices_from_cache(cfg, cache, rows)
  if cached_count > 0:
    log(f"Loaded {cached_count} prices from cache.")
  if releases_needing_fetch:
    _fetch_and_cache_prices(cfg, log, progress_callback, cache, headers, releases_needing_fetch, cached_count, main_progress_q)
  else:
    log("All prices loaded from cache.")
    if main_progress_q:
      main_progress_q.put(("update", "All prices loaded from cache."))

def _populate_prices_from_cache(cfg, cache, rows):
    releases_needing_fetch = []
    cached_count = 0
    if cache:
        for row in rows:
            if row.release_id:
                lowest, num_for_sale, is_stale = cache.get_price(row.release_id, cfg.currency)
                if not is_stale and lowest is not None:
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
    return releases_needing_fetch, cached_count

def _fetch_and_cache_prices(cfg, log, progress_callback, cache, headers, releases_needing_fetch, cached_count, main_progress_q=None):
  total_to_fetch = len([r for r in releases_needing_fetch if r.release_id])
  log(f"Fetching {total_to_fetch} prices ({cfg.currency})...")
  if progress_callback:
    progress_callback("show", f"Fetching {total_to_fetch} album prices in {cfg.currency}.\n({cached_count} loaded from cache)")
  if main_progress_q:
    main_progress_q.put(("update", f"Fetching {total_to_fetch} album prices in {cfg.currency}..."))
  fetched_count = [0]
  def price_progress(msg: str):
    fetched_count[0] += 1
    log(msg)
    if progress_callback:
      progress_callback("update", f"[{fetched_count[0]}/{total_to_fetch}] {msg}")
    if main_progress_q:
      main_progress_q.put(("update", f"[{fetched_count[0]}/{total_to_fetch}] {msg}"))
  try:
    core.fetch_prices_for_rows(headers, releases_needing_fetch, currency=cfg.currency, log_callback=price_progress, debug=False)
  except Exception as e:
    if main_progress_q:
      main_progress_q.put(("error", f"Price fetch failed: {e}"))
    raise
  if cache:
    for row in releases_needing_fetch:
      if row.release_id and row.lowest_price is not None:
        cache.set_price(row.release_id, cfg.currency, row.lowest_price, row.num_for_sale)
      elif row.release_id:
        cache.set_price(row.release_id, cfg.currency, None, 0)
    cache.save()
  log("Price fetch complete.")
  if main_progress_q:
    main_progress_q.put(("update", "Price fetch complete."))
  if progress_callback:
    progress_callback("close", None)


class App:

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
    
    # Drag-and-drop state
    self._drag_start_index: int | None = None
    self._drag_item_id: str | None = None

    self._build_ui(root)
    
    # Secondary button style - subtle
    SECONDARY_TBUTTON_STYLE = "Secondary.TButton"
    self.style.configure(SECONDARY_TBUTTON_STYLE,
                         background=c["panel2"],
                         foreground=c["text"],
                         borderwidth=0,
                         lightcolor=c["panel2"],
                         darkcolor=c["panel2"],
                         padding=(16, 10),
                         font=(FONT_SEGOE_UI, 10))
    self.style.map(SECONDARY_TBUTTON_STYLE,
                   background=[("active", c["order_bg"])])
    
    # Danger button style (red) - matching rounded feel
    DANGER_TBUTTON_STYLE = "Danger.TButton"
    self.style.configure(DANGER_TBUTTON_STYLE,
                         background=c["accent3"],
                         foreground="#ffffff",
                         borderwidth=0,
                         lightcolor=c["accent3"],
                         darkcolor=c["accent3"],
                         padding=(20, 12),
                         font=(FONT_SEGOE_UI_SEMIBOLD, 10))
    self.style.map(DANGER_TBUTTON_STYLE,
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
                         font=(FONT_SEGOE_UI, 10))
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
      self.root.option_add("*TCombobox*Listbox.font", (FONT_SEGOE_UI, 10))
    except Exception:
      pass
    
    # Checkbutton style - clean modern look
    self.style.configure("TCheckbutton",
                         background=c["panel"],
                         foreground=c["text"],
                         focuscolor=c["panel"],
                         font=(FONT_SEGOE_UI, 10))
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
                         font=(FONT_SEGOE_UI_SEMIBOLD, 10))
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
                         rowheight=44)
    self.style.configure(f"{style_name}.Heading",
                         background=c["panel2"],
                         foreground=c["text"],
                         relief="flat",
                         borderwidth=0)
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
                         rowheight=44)
    self.style.configure("Treeview.Heading",
                         background=c["panel2"],
                         foreground=c["text"],
                         relief="flat",
                         borderwidth=0)
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
    # Main container - let ttkbootstrap handle styling
    import tkinter as tk
    frm = ttk.Frame(root)
    frm.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frm.columnconfigure(0, weight=0)  # Settings column (fixed width)
    frm.columnconfigure(1, weight=1)  # Main content column (expands)

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
      font=(FONT_SEGOE_UI_SEMIBOLD, 22),
      padx=20,
      pady=14,
    )
    self._header_title.grid(row=1, column=0, sticky="w")
    self._header_subtitle = tk.Label(
      self._header,
      text="Vinyl Collection Manager  •  Live Updates  •  Export & Print",
      bg=self._colors["bg"],
      fg=self._colors["muted"],
      font=(FONT_SEGOE_UI, 11),
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
      font=(FONT_SEGOE_UI_SEMIBOLD, 10),
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

    # ===== SIDE-BY-SIDE LAYOUT =====
    # Left: Settings panel (fixed width)
    # Right: Main content (search, buttons, shelf list)
    
    frm.rowconfigure(row, weight=1)  # This row expands
    
    # Settings card - LEFT COLUMN (narrow, fixed width)
    self._settings_frame = tk.LabelFrame(
      frm, 
      text="⚙️ Settings",
      font=(FONT_SEGOE_UI_SEMIBOLD, 11),
      bg=self._colors["panel"],
      fg=self._colors["accent"],
      bd=1,
      relief="groove",
      padx=8,
      pady=8,
    )
    self._settings_frame.grid(row=row, column=0, sticky="nsew", padx=(12, 6), pady=8)
    settings = self._settings_frame  # Alias for backward compatibility
    srow = 0
    
    # Helper to create dark-themed entry widgets
    def make_entry(parent, textvar, width=28, show=""):
      e = tk.Entry(
        parent, 
        textvariable=textvar, 
        width=width,
        show=show,
        font=(FONT_SEGOE_UI, 10),
        bg=self._colors["order_bg"],
        fg=self._colors["order_fg"],
        insertbackground=self._colors["order_fg"],
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=self._colors["panel2"],
        highlightcolor=self._colors["accent"],
      )
      return e

    tk.Label(settings, text="Token", font=(FONT_SEGOE_UI, 10), bg=self._colors["panel"], fg=self._colors["text"]).grid(row=srow, column=0, sticky="w", padx=4, pady=4)
    self.token_entry = make_entry(settings, self.v_token, width=24, show="•")
    self.token_entry.grid(row=srow, column=1, sticky="ew", padx=4, pady=4, ipady=4)
    ttk.Checkbutton(settings, text="Show", variable=self.v_show_token, command=self._toggle_token_visibility).grid(row=srow, column=2, sticky="w", padx=4, pady=4)
    srow += 1

    # User-Agent - hidden but still in code for API requests
    self._useragent_entry = make_entry(settings, self.v_user_agent)
    # Don't grid it - hidden from UI

    self._out_row = tk.Frame(settings, bg=self._colors["panel"])
    self._out_row.grid(row=srow, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
    self._out_row.columnconfigure(0, weight=1)
    tk.Label(self._out_row, text="Output Dir", font=(FONT_SEGOE_UI, 10), bg=self._colors["panel"], fg=self._colors["text"]).grid(row=0, column=0, sticky="w", columnspan=2)
    self._output_entry = make_entry(self._out_row, self.v_output_dir, width=20)
    self._output_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0), ipady=4)
    # Use bootstyle for rounded buttons
    if TTKBOOTSTRAP_AVAILABLE:
      self._browse_btn = ttk.Button(self._out_row, text="📂", bootstyle="info-outline", command=self._choose_dir, width=3)
      self._browse_btn.grid(row=1, column=1, sticky="e", padx=(4, 0))
    else:
      self._browse_btn = ttk.Button(self._out_row, text="📂", command=self._choose_dir, width=3)
      self._browse_btn.grid(row=1, column=1, sticky="e", padx=(4, 0))
    self._open_btn = None  # Removed to save space
    srow += 1

    # Options in a more compact vertical layout
    self._opt_row = tk.Frame(settings, bg=self._colors["panel"])
    self._opt_row.grid(row=srow, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
    
    # Poll row
    poll_frame = tk.Frame(self._opt_row, bg=self._colors["panel"])
    poll_frame.grid(row=0, column=0, sticky="w", pady=2)
    tk.Label(poll_frame, text="Poll (sec)", font=(FONT_SEGOE_UI, 9), bg=self._colors["panel"], fg=self._colors["text"]).grid(row=0, column=0, sticky="w")
    self._poll_spin = tk.Spinbox(
      poll_frame, from_=15, to=3600, textvariable=self.v_poll, width=6,
      font=(FONT_SEGOE_UI, 9),
      bg=self._colors["order_bg"],
      fg=self._colors["order_fg"],
      buttonbackground=self._colors["panel2"],
      insertbackground=self._colors["order_fg"],
      relief="flat",
      bd=0,
      highlightthickness=1,
      highlightbackground=self._colors["panel2"],
      highlightcolor=self._colors["accent"],
    )
    self._poll_spin.grid(row=0, column=1, padx=(4, 0), ipady=2)
    
    # Checkboxes - stacked vertically
    self._json_check = ttk.Checkbutton(self._opt_row, text="Also export JSON", variable=self.v_json)
    self._json_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
    self._prices_check = ttk.Checkbutton(self._opt_row, text="Show Prices", variable=self.v_show_prices)
    self._prices_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
    
    # Currency row
    currency_frame = tk.Frame(self._opt_row, bg=self._colors["panel"])
    currency_frame.grid(row=3, column=0, columnspan=2, sticky="w", pady=2)
    tk.Label(currency_frame, text="Currency", font=(FONT_SEGOE_UI, 9), bg=self._colors["panel"], fg=self._colors["text"]).grid(row=0, column=0, sticky="w")
    self._currency_combo = tk.OptionMenu(currency_frame, self.v_currency, "USD", "EUR", "GBP", "SEK", "CAD", "AUD", "JPY")
    self._currency_combo.config(
      font=(FONT_SEGOE_UI, 9),
      bg=self._colors["order_bg"],
      fg=self._colors["order_fg"],
      activebackground=self._colors["accent"],
      activeforeground="#ffffff",
      highlightthickness=0,
      bd=0,
      relief="flat",
      width=6,
    )
    self._currency_combo["menu"].config(
      bg=self._colors["order_bg"],
      fg=self._colors["order_fg"],
      activebackground=self._colors["accent"],
      activeforeground="#ffffff",
    )
    self._currency_combo.grid(row=0, column=1, padx=(4, 0))
    
    # Refresh prices button
    if TTKBOOTSTRAP_AVAILABLE:
      self._refresh_prices_btn = ttk.Button(self._opt_row, text="🔄 Refresh Prices", bootstyle="warning-outline", command=self._refresh_prices)
    else:
      self._refresh_prices_btn = ttk.Button(self._opt_row, text="🔄 Refresh Prices", command=self._refresh_prices)
    self._refresh_prices_btn.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
    srow += 1

    # Sort options row
    self._sort_row = tk.Frame(settings, bg=self._colors["panel"])
    self._sort_row.grid(row=srow, column=0, columnspan=3, sticky="ew", padx=4, pady=4)
    tk.Label(self._sort_row, text="Sort By", font=(FONT_SEGOE_UI, 9), bg=self._colors["panel"], fg=self._colors["text"]).grid(row=0, column=0, sticky="w")
    sort_options = ["artist", "title", "year", "price_asc", "price_desc"]
    self._sort_combo = tk.OptionMenu(self._sort_row, self.v_sort_by, *sort_options)
    self._sort_combo.config(
      font=(FONT_SEGOE_UI, 9),
      bg=self._colors["order_bg"],
      fg=self._colors["order_fg"],
      activebackground=self._colors["accent"],
      activeforeground="#ffffff",
      highlightthickness=0,
      bd=0,
      relief="flat",
      width=10,
    )
    self._sort_combo["menu"].config(
      bg=self._colors["order_bg"],
      fg=self._colors["order_fg"],
      activebackground=self._colors["accent"],
      activeforeground="#ffffff",
    )
    self._sort_combo.grid(row=0, column=1, padx=(4, 0), sticky="w")
    srow += 1
    
    # Price info note (compact)
    self._price_info = tk.Frame(settings, bg=self._colors["panel"])
    self._price_info.grid(row=srow, column=0, columnspan=3, sticky="ew", padx=4, pady=(8, 4))
    tk.Label(self._price_info, text="ℹ️ Prices = lowest listed\nfor your specific pressing", font=(FONT_SEGOE_UI, 8), bg=self._colors["panel"], fg=self._colors["muted"], justify="left").grid(row=0, column=0, sticky="w")
    srow += 1

    # ===== RIGHT COLUMN: Main content (Search, buttons, shelf list) =====
    main_content = ttk.Frame(frm)
    main_content.grid(row=row, column=1, sticky="nsew", padx=(6, 12), pady=8)
    main_content.columnconfigure(0, weight=1)
    main_content.rowconfigure(2, weight=1)  # Notebook row expands
    
    mc_row = 0

    # Search row with styled entry
    search_row = ttk.Frame(main_content)
    search_row.grid(row=mc_row, column=0, sticky="ew", pady=(0, 8))
    search_row.columnconfigure(1, weight=1)
    ttk.Label(search_row, text="🔍 Search").grid(row=0, column=0, sticky="w")
    
    # Use tk.Entry for full color control in dark mode
    self._search_entry = tk.Entry(
      search_row, 
      textvariable=self.v_search,
      font=(FONT_SEGOE_UI, 11),
      bg=self._colors["order_bg"],
      fg=self._colors["order_fg"],
      insertbackground=self._colors["order_fg"],
      relief="flat",
      bd=0,
      highlightthickness=1,
      highlightbackground=self._colors["panel2"],
      highlightcolor=self._colors["accent"],
    )
    self._search_entry.grid(row=0, column=1, sticky="ew", padx=6, ipady=6)
    # Use bootstyle for ttkbootstrap rounded buttons
    if TTKBOOTSTRAP_AVAILABLE:
      self._clear_btn = ttk.Button(search_row, text="✕ Clear", bootstyle="secondary-outline", command=lambda: self.v_search.set(""))
      self._clear_btn.grid(row=0, column=2, sticky="e")
    else:
      self._clear_btn = ttk.Button(search_row, text="✕ Clear", style=SECONDARY_TBUTTON_STYLE, command=lambda: self.v_search.set(""))
      self._clear_btn.grid(row=0, column=2, sticky="e")
    ttk.Label(search_row, textvariable=self.v_match).grid(row=0, column=3, sticky="e", padx=6)
    self.v_search.trace_add("write", lambda *_: self._on_search_change())
    mc_row += 1

    # Action buttons row with styled buttons
    btn = ttk.Frame(main_content)
    btn.grid(row=mc_row, column=0, sticky="ew", pady=(0, 8))
    btn.columnconfigure(0, weight=1)
    btn.columnconfigure(1, weight=1)
    btn.columnconfigure(2, weight=1)
    btn.columnconfigure(3, weight=1)
    
    # Use ttkbootstrap bootstyle for rounded corners, or fall back to custom styles
    if TTKBOOTSTRAP_AVAILABLE:
      self._refresh_btn = ttk.Button(btn, text="🔄 Refresh", bootstyle="primary", command=self._refresh_now)
      self._refresh_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
      self._export_btn = ttk.Button(btn, text="📁 Export", bootstyle="success", command=self._export_files)
      self._export_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=4)
      self._print_btn = ttk.Button(btn, text="🖨️ Print", bootstyle="secondary", command=self._print_current)
      self._print_btn.grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=4)
      self._stop_btn = ttk.Button(btn, text="⏹️ Stop", bootstyle="danger", command=self._stop_app)
      self._stop_btn.grid(row=0, column=3, sticky="ew", pady=4)
    else:
      PRIMARY_TBUTTON_STYLE = "Primary.TButton"
      SUCCESS_TBUTTON_STYLE = "Success.TButton"
      DANGER_TBUTTON_STYLE = "Danger.TButton"
      self._refresh_btn = ttk.Button(btn, text="🔄 Refresh", style=PRIMARY_TBUTTON_STYLE, command=self._refresh_now)
      self._refresh_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
      self._export_btn = ttk.Button(btn, text="📁 Export", style=SUCCESS_TBUTTON_STYLE, command=self._export_files)
      self._export_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=4)
      self._print_btn = ttk.Button(btn, text="🖨️ Print", style=SECONDARY_TBUTTON_STYLE, command=self._print_current)
      self._print_btn.grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=4)
      self._stop_btn = ttk.Button(btn, text="⏹️ Stop", style=DANGER_TBUTTON_STYLE, command=self._stop_app)
      self._stop_btn.grid(row=0, column=3, sticky="ew", pady=4)
    mc_row += 1

    nb = ttk.Notebook(main_content)
    nb.grid(row=mc_row, column=0, sticky="nsew")

    order_fr = ttk.Frame(nb)
    nb.add(order_fr, text="📋 Shelf Order")

    # --- Wishlist Tab (modular) ---
    nb.add(self._wishlist_tab.get_frame(), text="⭐ Wishlist")

    order_fr.rowconfigure(1, weight=1)
    order_fr.columnconfigure(0, weight=1)
    
    # Toolbar for manual ordering controls
    order_toolbar = ttk.Frame(order_fr)
    order_toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
    
    self._manual_order_check = ttk.Checkbutton(
      order_toolbar, 
      text="✋ Manual Order Mode", 
      variable=self.v_manual_order_enabled,
      command=self._toggle_manual_order
    )
    self._manual_order_check.grid(row=0, column=0, sticky="w", padx=(0, 16))
    
    self._manual_order_hint = ttk.Label(
      order_toolbar,
      text="(Drag rows to reorder)",
      foreground=self._colors["muted"]
    )
    self._manual_order_hint.grid(row=0, column=1, sticky="w", padx=(0, 16))
    
    if TTKBOOTSTRAP_AVAILABLE:
      self._reset_order_btn = ttk.Button(
        order_toolbar, 
        text="↺ Reset to Auto Sort", 
        bootstyle="warning-outline",
        command=self._reset_manual_order
      )
    else:
      self._reset_order_btn = ttk.Button(
        order_toolbar, 
        text="↺ Reset to Auto Sort", 
        command=self._reset_manual_order
      )
    self._reset_order_btn.grid(row=0, column=2, sticky="e", padx=(0, 8))
    
    # Move up/down buttons for keyboard users
    if TTKBOOTSTRAP_AVAILABLE:
      self._move_up_btn = ttk.Button(order_toolbar, text="▲ Up", bootstyle="secondary-outline", command=self._move_item_up)
      self._move_down_btn = ttk.Button(order_toolbar, text="▼ Down", bootstyle="secondary-outline", command=self._move_item_down)
    else:
      self._move_up_btn = ttk.Button(order_toolbar, text="▲ Up", command=self._move_item_up)
      self._move_down_btn = ttk.Button(order_toolbar, text="▼ Down", command=self._move_item_down)
    self._move_up_btn.grid(row=0, column=3, sticky="e", padx=(8, 4))
    self._move_down_btn.grid(row=0, column=4, sticky="e", padx=(0, 8))
    
    order_toolbar.columnconfigure(1, weight=1)

    order_wrap = ttk.Frame(order_fr)
    order_wrap.grid(row=1, column=0, sticky="nsew", padx=(12, 0), pady=(0, 8))
    order_wrap.rowconfigure(0, weight=1)
    order_wrap.columnconfigure(0, weight=1)

    order_scroll = ttk.Scrollbar(order_wrap, orient="vertical")
    order_scroll.grid(row=0, column=1, sticky="ns")

    # Use Treeview for drag-and-drop support
    # Note: "#0" column (tree column) is used for album artwork
    columns = ("#", "Artist", "Title", "Year", "Label", "Price")
    
    # Determine style based on current theme
    tree_style = "Dark.Treeview" if self.v_dark_mode.get() else "Light.Treeview"
    
    self.order_tree = ttk.Treeview(
      order_wrap,
      columns=columns,
      show="tree headings",  # Show both tree column (for images) and headings
      yscrollcommand=order_scroll.set,
      selectmode="browse",  # Single selection for drag-drop
      style=tree_style,
    )
    self.order_tree.grid(row=0, column=0, sticky="nsew")
    order_scroll.config(command=self.order_tree.yview)
    
    # Configure the #0 (tree) column for album artwork
    self.order_tree.heading("#0", text="", anchor="center")
    self.order_tree.column("#0", width=50, minwidth=50, stretch=False, anchor="center")
    
    # Configure column headings and widths
    self.order_tree.heading("#", text="#", anchor="center")
    self.order_tree.heading("Artist", text="Artist", anchor="w")
    self.order_tree.heading("Title", text="Title", anchor="w")
    self.order_tree.heading("Year", text="Year", anchor="center")
    self.order_tree.heading("Label", text="Label / Cat#", anchor="w")
    self.order_tree.heading("Price", text="Price", anchor="e")
    
    # Column widths - text columns stretch proportionally to fill width
    self.order_tree.column("#", width=35, minwidth=30, stretch=False, anchor="center")
    self.order_tree.column("Artist", width=200, minwidth=100, stretch=True, anchor="w")
    self.order_tree.column("Title", width=260, minwidth=120, stretch=True, anchor="w")
    self.order_tree.column("Year", width=50, minwidth=45, stretch=False, anchor="center")
    self.order_tree.column("Label", width=280, minwidth=100, stretch=True, anchor="w")
    self.order_tree.column("Price", width=80, minwidth=70, stretch=False, anchor="e")
    
    # Initially hide Price column if Show Prices is disabled
    if not self.v_show_prices.get():
      self.order_tree.column("Price", width=0, minwidth=0, stretch=False)
    
    # Configure row tags for alternating colors (with foreground for dark mode)
    self.order_tree.tag_configure("row_even", background=self._colors["order_bg"], foreground=self._colors["order_fg"])
    self.order_tree.tag_configure("row_odd", background="#1a2d4d" if self.v_dark_mode.get() else "#f0f4f8", foreground=self._colors["order_fg"])
    self.order_tree.tag_configure("search_match", background="#fbbf24", foreground="#1a1a2e")
    self.order_tree.tag_configure("dragging", background=self._colors["accent"], foreground="#ffffff")
    
    # Configure Treeview style for dark mode
    self._configure_treeview_style()
    
    # Bind drag-and-drop events
    self.order_tree.bind("<ButtonPress-1>", self._on_drag_start)
    self.order_tree.bind("<B1-Motion>", self._on_drag_motion)
    self.order_tree.bind("<ButtonRelease-1>", self._on_drag_end)
    
    # Bind hover events for album artwork preview
    self.order_tree.bind("<Motion>", self._on_tree_motion)
    self.order_tree.bind("<Leave>", self._on_tree_leave)

    # Bind double-click to show album info popup
    self.order_tree.bind("<Double-1>", self._on_album_double_click)

    # ...existing code...
    # Bind double-click to show album info popup
    self.order_tree.bind("<Double-1>", self._on_album_double_click)

    # Initialize image preview popup
    self._image_preview = ImagePreviewPopup(self.root, self._thumbnail_cache)
    self._hover_release_id: int | None = None

    # Keep Text widget reference for backward compatibility (hidden)
    self.order_text = tk.Text(order_wrap, height=1, width=1)
    # Don't grid it - it's just for compatibility with existing code

    # Store reference to rows for drag-drop operations
    self._tree_rows: list[ReleaseRow] = []

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
    )
    self.log.grid(row=0, column=0, sticky="nsew")
    log_scroll.config(command=self.log.yview)

  def _on_album_double_click(self, event):
    """Show a popup with album details when a row is double-clicked."""
    item_id = self.order_tree.identify_row(event.y)
    row = self._get_row_from_item_id(item_id)
    if not row:
      return
    AlbumPopup(
      self.root,
      row,
      self._thumbnail_cache,
      self._colors,
      on_spotify=lambda r: self._play_on_spotify(r),
      on_wishlist=lambda r: self._toggle_wishlist(r)
    )

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
    # Try to load the preview image for the release (works for both shelf and wishlist rows)
    if hasattr(self, '_thumbnail_cache') and getattr(row, 'release_id', None):
      cover_img = self._thumbnail_cache.load_preview(row.release_id, getattr(row, 'cover_image_url', None))
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
      ("Label", getattr(row, "label", "")),
      ("Catalog #", getattr(row, "catno", "")),
      ("Format", getattr(row, "format_str", getattr(row, "format", ""))),
      ("Country", getattr(row, "country", "")),
      ("Price", f"{getattr(row, 'lowest_price', '')} {getattr(row, 'price_currency', '')}" if getattr(row, "lowest_price", None) is not None else ""),
      ("Discogs ID", getattr(row, "release_id", "")),
      ("Master ID", getattr(row, "master_id", "")),
      ("Barcode", getattr(row, "barcode", "")),
      ("Companies", getattr(row, "companies", "")),
      ("Contributors", getattr(row, "contributors", "")),
      ("URL", getattr(row, "discogs_url", getattr(row, "url", ""))),
      ("Genres", getattr(row, "genres", "")),
      ("Styles", getattr(row, "styles", "")),
      ("Notes", getattr(row, "notes", "")),
      ("Tracklist", getattr(row, "tracklist", "")),
      ("Extra", getattr(row, "extra", "")),
    ]
    for i, (label, value) in enumerate(details):
      if value:
        tk.Label(details_frame, text=label+":", anchor="e", font=(FONT_SEGOE_UI, 14, "bold"), bg=bg, fg=fg).grid(row=i+row_offset, column=0, sticky="e", padx=(0,18), pady=10)
        tk.Label(details_frame, text=str(value), anchor="w", font=(FONT_SEGOE_UI, 14), bg=bg, fg=fg, wraplength=480, justify="left").grid(row=i+row_offset, column=1, sticky="w", padx=(0,12), pady=10)

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

  def _add_popup_buttons(self, popup, row, accent, btn_bg, btn_fg, bg):
    # Use the stacked button frame if present (from _add_album_cover_to_popup)
    btn_frame = getattr(popup, '_btn_stack', None)
    if btn_frame is None:
        btn_frame = tk.Frame(popup.outer, bg=bg)
        btn_frame.pack(fill="x", pady=(12,0))

    url = getattr(row, "url", "")
    if url:
        def open_url():
            import webbrowser
            webbrowser.open(url)
        btn = tk.Button(btn_frame, text="Open in Discogs", command=open_url, font=(FONT_SEGOE_UI, 13), bg=accent, fg=btn_fg, activebackground=btn_bg, activeforeground=btn_fg, relief="groove")
        btn.pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)

    # Play on Spotify button
    def play_on_spotify():
        from core.spotify_utils import open_album_on_spotify
        artist = getattr(row, "artist_display", "")
        album = getattr(row, "title", "")
        open_album_on_spotify(artist, album)
    btn_spotify = tk.Button(
        btn_frame, text="Play on Spotify", command=play_on_spotify,
        font=(FONT_SEGOE_UI, 13), bg="#1db954", fg="#fff", activebackground="#1ed760", activeforeground="#fff", relief="groove"
    )
    btn_spotify.pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)

    # Wishlist button
    from core.wishlist import add_to_wishlist, remove_from_wishlist, is_in_wishlist
    artist = getattr(row, "artist_display", "")
    album = getattr(row, "title", "")
    discogs_url = getattr(row, "discogs_url", getattr(row, "url", None))
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
            add_to_wishlist(artist, album, discogs_url)
        update_wishlist_state()
    update_wishlist_state()
    btn_wishlist = tk.Button(
        btn_frame, textvariable=wishlist_state, command=toggle_wishlist,
        font=(FONT_SEGOE_UI, 13), bg="#ffb347", fg="#222", activebackground="#ffd580", activeforeground="#222", relief="groove"
    )
    btn_wishlist.pack(side="top", fill="x", padx=12, pady=(0, 8), ipadx=12, ipady=4)

    tk.Button(btn_frame, text="Close", command=popup.destroy, font=(FONT_SEGOE_UI, 13), bg=btn_bg, fg=btn_fg, activebackground=accent, activeforeground=btn_fg, relief="groove").pack(side="top", fill="x", padx=12, pady=(0, 0), ipadx=12, ipady=4)

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
        from discogs_app import make_headers
        headers = make_headers(self.v_token.get(), self.v_user_agent.get())
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
      import platform
      if platform.system() == "Windows":
        os.startfile(path)
      elif platform.system() == "Darwin":
        subprocess.run(["open", path], check=False)
      else:
        subprocess.run(["xdg-open", path], check=False)
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
    self._set_theme_colors()
    self._configure_styles()
    self._update_theme_button()
    self._update_header()
    self._update_status_bar_widgets()
    self._update_treeview_widget()
    self._update_search_entry()
    self._update_settings_entries()
    self._update_settings_frames()
    self._update_log_widget()
    self._update_root_bg()

  def _set_theme_colors(self):
    if self.v_dark_mode.get():
      self._colors = self._dark_colors.copy()
      self.theme_btn.config(text="🌙 Dark")
      if TTKBOOTSTRAP_AVAILABLE:
        self.style.theme_use("darkly")
    else:
      self._colors = self._light_colors.copy()
      self.theme_btn.config(text="☀️ Light")
      if TTKBOOTSTRAP_AVAILABLE:
        self.style.theme_use("litera")

  def _update_theme_button(self):
    self.theme_btn.config(
      bg=self._colors["accent"],
      fg="#ffffff",
      activebackground=self._colors["button_hover"],
      activeforeground="#ffffff"
    )

  def _update_header(self):
    try:
      self._header.config(bg=self._colors["bg"])
      self._header_title.config(bg=self._colors["bg"], fg=self._colors["text"])
      self._header_subtitle.config(bg=self._colors["bg"], fg=self._colors["muted"])
      for child in self._header.winfo_children():
        if child.winfo_class() == "Frame" and child.cget("height") == 4:
          child.config(bg=self._colors["accent"])
    except Exception:
      pass

  def _update_status_bar_widgets(self):
    try:
      self._status_bar.config(bg=self._colors["accent"])
      self._status_label.config(bg=self._colors["accent"], fg="#ffffff")
      for widget in [self._count_icon, self._count_label, self._sync_icon, self._sync_label, 
                     self._value_sep, self._value_icon, self._value_label]:
        try:
          widget.config(bg=self._colors["accent"])
        except Exception:
          pass
      for child in self._status_bar.winfo_children():
        try:
          child.config(bg=self._colors["accent"])
        except Exception:
          pass
    except Exception:
      pass

  def _update_treeview_widget(self):
    try:
      self._configure_treeview_style()
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

  def _update_search_entry(self):
    try:
      self._search_entry.config(
        bg=self._colors["order_bg"],
        fg=self._colors["order_fg"],
        insertbackground=self._colors["order_fg"],
        highlightbackground=self._colors["panel2"],
        highlightcolor=self._colors["accent"],
      )
    except Exception:
      pass

  def _update_settings_entries(self):
    try:
      entry_config = {
        "bg": self._colors["order_bg"],
        "fg": self._colors["order_fg"],
        "insertbackground": self._colors["order_fg"],
        "highlightbackground": self._colors["panel2"],
        "highlightcolor": self._colors["accent"],
      }
      for widget in [self.token_entry, self._useragent_entry, self._output_entry]:
        try:
          widget.config(**entry_config)
        except Exception:
          pass
      self._poll_spin.config(
        bg=self._colors["order_bg"],
        fg=self._colors["order_fg"],
        buttonbackground=self._colors["panel2"],
        insertbackground=self._colors["order_fg"],
        highlightbackground=self._colors["panel2"],
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
    try:
      self._settings_frame.config(
        bg=self._colors["panel"],
        fg=self._colors["accent"],
      )
      frame_config = {"bg": self._colors["panel"]}
      for frame in [self._out_row, self._opt_row, self._sort_row, self._price_info]:
        try:
          frame.config(**frame_config)
          for child in frame.winfo_children():
            if child.winfo_class() == "Label":
              try:
                child.config(bg=self._colors["panel"])
              except Exception:
                pass
        except Exception:
          pass
    except Exception:
      pass

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
    try:
      self.root.config(bg=self._colors["panel2"])
    except Exception:
      pass

  def _log(self, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    self.log_q.put(f"[{ts}] {msg}\n")

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
        action, message = self.progress_q.get_nowait()
        self._process_progress_action(action, message)
    except queue.Empty:
      pass

  def _process_progress_action(self, action: str, message: str | None) -> None:
    if action == "show":
      self._set_action_buttons_state("disabled")
      if self._progress_dialog is None:
        self._progress_dialog = ProgressDialog(self.root, "Working...", message or "Please wait...")
    elif action == "update" and self._progress_dialog is not None:
      self._progress_dialog.update_progress(message or "")
    elif action == "message" and self._progress_dialog is not None:
      self._progress_dialog.update_message(message or "")
    elif action == "error" and self._progress_dialog is not None:
      self._progress_dialog.set_error(message or "An error occurred.")
      self._progress_dialog.top.after(1600, self._progress_dialog.close)
      self._progress_dialog = None
      self._set_action_buttons_state("normal")
    elif action == "done" and self._progress_dialog is not None:
      self._progress_dialog.set_done(message or "Done!")
      self._progress_dialog = None
      self._set_action_buttons_state("normal")
    elif action == "close" and self._progress_dialog is not None:
      self._progress_dialog.close()
      self._progress_dialog = None
      self._set_action_buttons_state("normal")

  def _render_order(self, result: BuildResult) -> None:
    """Render the shelf order in the Treeview widget."""
    self._clear_treeview()
    if not result.rows_sorted:
      self._tree_rows = []
      self.v_match.set("0 items")
      return

    rows = self._apply_manual_order_if_enabled(result)
    self._tree_rows = list(rows)
    self._show_or_hide_price_column()
    placeholder = self._get_placeholder_image()
    self._populate_treeview_rows(rows, placeholder)
    self.v_match.set(f"{len(rows)} items")
    self._highlight_search()
    if self._thumbnails_enabled:
      self._download_missing_thumbnails(rows)

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
    if self._thumbnails_enabled and row.release_id:
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
      from discogs_app import make_headers
      headers = make_headers(self.v_token.get(), self.v_user_agent.get())
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
    if not self._last_result or not self._thumbnails_enabled:
      return
    
    # Update each item with its thumbnail
    items = self.order_tree.get_children()
    rows = self._tree_rows
    
    for i, (item, row) in enumerate(zip(items, rows)):
      if row.release_id:
        img = self._thumbnail_cache.load_photo(row.release_id)
        if img:
          self.order_tree.item(item, image=img)

  def _update_status_bar(self, result: BuildResult) -> None:
    """Update the status bar with collection info."""
    from datetime import datetime

    self._update_collection_count(result)
    self._update_last_sync()
    self._update_total_value_section(result)

  def _update_collection_count(self, result: BuildResult) -> None:
    count = len(result.rows_sorted)
    self.v_collection_count.set(f"{count} albums")

  def _update_last_sync(self) -> None:
    from datetime import datetime
    now = datetime.now()
    self.v_last_sync.set(f"Synced {now.strftime('%H:%M')}")

  def _update_total_value_section(self, result: BuildResult) -> None:
    if self.v_show_prices.get() and result.rows_sorted:
      total_value, priced_count, currency = self._calculate_total_value(result.rows_sorted)
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
    for attr in ['_value_sep', '_value_icon', '_value_label']:
      if hasattr(self, attr):
        getattr(self, attr).grid()

  def _hide_value_section(self) -> None:
    for attr in ['_value_sep', '_value_icon', '_value_label']:
      if hasattr(self, attr):
        getattr(self, attr).grid_remove()

  def _highlight_search(self) -> None:
    """Highlight matching rows in the Treeview based on search query."""
    q = (self.v_search.get() or "").strip().lower()
    self._reset_treeview_tags()
    if not q:
      self._set_match_count_label()
      return
    matches, first_match_item = self._find_and_highlight_matches(q)
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
    
    # Use the current display order (which respects manual ordering)
    rows_to_export = self._tree_rows if self._tree_rows else result.rows_sorted

    txt_path = out_dir / "vinyl_shelf_order.txt"
    csv_path = out_dir / "vinyl_shelf_order.csv"
    core.write_txt(rows_to_export, txt_path, dividers=False, align=False, show_country=False)
    core.write_csv(rows_to_export, csv_path)
    self._log(f"Exported: {txt_path.name}")
    self._log(f"Exported: {csv_path.name}")

    if cfg.write_json:
      json_path = out_dir / "vinyl_shelf_order.json"
      core.write_json(rows_to_export, json_path)
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

    if not messagebox.askyesno("Print", "Send the current shelf order to your default printer?"):
      return
    
    # Generate printable text from current order
    lines = []
    for i, row in enumerate(self._tree_rows):
      line = f"{i+1:3d}. {row.artist_display} — {row.title}"
      if row.year:
        line += f" ({row.year})"
      lines.append(line)

    # Try Windows printing first, fall back to lpr
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

  def _watch_loop(self) -> None:
    """Background thread: poll collection count; rebuild on change or manual refresh."""
    self._log("Watcher started.")
    self.v_status.set("Watching for changes…")

    def progress_callback(action: str, message: str | None):
      self.progress_q.put((action, message))

    while not self._stop.is_set():
      cfg = self._get_cfg()
      try:
        if not self._has_valid_token(cfg):
          self._handle_missing_token(cfg)
          continue

        _, headers, username = self._get_user_info(cfg)
        count = get_collection_count(headers, username)
        force = self._force_rebuild
        self._force_rebuild = False

        if self._should_build_initial(force):
          self._handle_initial_build(cfg, count, progress_callback)
        elif count != self._last_count:
          self._handle_collection_changed(cfg, count, progress_callback)
        else:
          self.v_status.set(f"No changes. Polling every {cfg.poll_seconds}s")

      except Exception as e:
        self._handle_watch_exception(e)

      self._wake.clear()
      self._wake.wait(timeout=cfg.poll_seconds)

    self._log("Watcher stopped.")

  def _has_valid_token(self, cfg):
    return bool(cfg.token or os.environ.get("DISCOGS_TOKEN", ""))

  def _handle_missing_token(self, cfg):
    self._log("Error: No Discogs token provided. Enter your token in the Settings.")
    self.v_status.set("Error: No token (see Log tab)")
    self._wake.clear()
    self._wake.wait(timeout=cfg.poll_seconds)

  def _get_user_info(self, cfg):
    token = core.get_token(cfg.token or None)
    headers = core.discogs_headers(token, cfg.user_agent)
    ident = core.get_identity(headers)
    username = ident.get("username")
    if not username:
      raise RuntimeError("Could not determine username from token.")
    return token, headers, username

  def _should_build_initial(self, force):
    return self._last_count is None or force

  def _handle_initial_build(self, cfg, count, progress_callback):
    if self._last_count is None:
      self._last_count = count
      self._log(f"Initial collection count: {count}")
    else:
      self._log(f"Forced refresh. Collection count: {count}")
    # --- Update wishlist from Discogs ---
    try:
      from core.wishlist import save_wishlist
      from core.discogs_api import fetch_discogs_wantlist
      token = self.v_token.get().strip()
      if token:
        self._log("Updating wishlist from Discogs…")
        wantlist = fetch_discogs_wantlist(token)
        save_wishlist(wantlist)
        self._log(f"Wishlist updated from Discogs. {len(wantlist)} items.")
        # Refresh wishlist tab if function is available
        try:
          if hasattr(self, "refresh_wishlist_tree"):
            self.refresh_wishlist_tree()
        except Exception:
          pass
    except Exception as e:
      self._log(f"Failed to update wishlist from Discogs: {e}")
    # ---
    self._log("Building shelf order…")
    self.v_status.set("Building…")
    result = build_once(cfg, self._log, progress_callback, self._collection_cache, self.progress_q)
    self.result_q.put(result)
    self._last_built_at = time.time()
    self._log(f"Build complete. Items: {len(result.rows_sorted)}")
    self.v_status.set(f"Built {len(result.rows_sorted)} items. Polling every {cfg.poll_seconds}s")

  def _handle_collection_changed(self, cfg, count, progress_callback):
    self._log(f"Collection changed: {self._last_count} → {count}")
    self._last_count = count
    self._log("Rebuilding shelf order…")
    self.v_status.set("Rebuilding…")
    result = build_once(cfg, self._log, progress_callback, self._collection_cache, self.progress_q)
    self.result_q.put(result)
    self._last_built_at = time.time()
    self._log(f"Build complete. Items: {len(result.rows_sorted)}")
    self.v_status.set(f"Built {len(result.rows_sorted)} items. Polling every {cfg.poll_seconds}s")

  def _handle_watch_exception(self, e):
    self._log(f"Error: {e}")
    self._log(traceback.format_exc())
    self.v_status.set("Error (see Log tab).")
    self.progress_q.put(("close", None))


def main() -> None:
  # Use ttkbootstrap Window for better theming if available
  if TTKBOOTSTRAP_AVAILABLE:
    try:
      import ttkbootstrap as ttk_bs
      root = ttk_bs.Window(themename="darkly")
    except ImportError:
      root = Tk()
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
