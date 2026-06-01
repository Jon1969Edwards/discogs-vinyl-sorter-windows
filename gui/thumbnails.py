"""Album artwork thumbnail cache and hover preview for Treeview rows."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import tkinter as tk

from core.paths import project_root

THUMBNAIL_CACHE_DIR = project_root() / ".discogs_thumbnails"

if TYPE_CHECKING:
  from PIL import ImageTk


def _is_low_quality_discogs_url(url: str) -> bool:
  """Check if a Discogs image URL is low quality (small size or low quality setting)."""
  if not url:
    return True
  return "/q:40/" in url or "/h:150/" in url or "/w:150/" in url


def _fetch_hires_image_url(release_id: int, headers: dict) -> str | None:
  """Fetch the high-resolution primary image URL for a release from the Discogs API."""
  import requests

  try:
    url = f"https://api.discogs.com/releases/{release_id}"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 200:
      data = resp.json()
      images = data.get("images", [])
      if images:
        return images[0].get("uri") or images[0].get("resource_url")
  except Exception:
    pass
  return None


class ThumbnailCache:
  """Cache for album artwork thumbnails."""

  THUMB_SIZE = (40, 40)
  PREVIEW_SIZE = (200, 200)
  POPUP_SIZE = (300, 300)

  def __init__(self):
    self.cache_dir = THUMBNAIL_CACHE_DIR
    self.cache_dir.mkdir(exist_ok=True)
    self._photo_cache: dict[int, ImageTk.PhotoImage] = {}
    self._preview_cache: dict[int, ImageTk.PhotoImage] = {}
    self._popup_cache: dict[int, ImageTk.PhotoImage] = {}
    self._placeholder: ImageTk.PhotoImage | None = None
    self._pil_available = False
    self._check_pil()

  def _check_pil(self) -> None:
    try:
      from PIL import Image, ImageTk  # noqa: F401

      self._pil_available = True
    except ImportError:
      self._pil_available = False

  def is_available(self) -> bool:
    return self._pil_available

  def _get_cache_path(self, release_id: int, preview: bool = False) -> Path:
    suffix = "_preview" if preview else ""
    return self.cache_dir / f"{release_id}{suffix}.png"

  def has_cached(self, release_id: int) -> bool:
    return self._get_cache_path(release_id).exists()

  def get_photo(self, release_id: int) -> ImageTk.PhotoImage | None:
    return self._photo_cache.get(release_id)

  def get_placeholder(self) -> ImageTk.PhotoImage | None:
    if not self._pil_available:
      return None
    if self._placeholder is not None:
      return self._placeholder
    try:
      from PIL import Image, ImageDraw, ImageTk

      img = Image.new("RGBA", self.THUMB_SIZE, (60, 60, 80, 255))
      draw = ImageDraw.Draw(img)
      cx, cy = self.THUMB_SIZE[0] // 2, self.THUMB_SIZE[1] // 2
      r = min(cx, cy) - 4
      draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(100, 100, 120), width=2)
      draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(100, 100, 120))
      self._placeholder = ImageTk.PhotoImage(img)
      return self._placeholder
    except Exception:
      return None

  def download_thumbnail(self, release_id: int, thumb_url: str, headers: dict[str, str]) -> bool:
    if not self._pil_available or not thumb_url:
      return False
    cache_path = self._get_cache_path(release_id)
    if cache_path.exists():
      return True
    try:
      import requests
      from io import BytesIO

      from PIL import Image

      resp = requests.get(thumb_url, headers=headers, timeout=10)
      if resp.status_code != 200:
        return False
      img = Image.open(BytesIO(resp.content))
      img = img.convert("RGBA")
      img.thumbnail(self.THUMB_SIZE, Image.Resampling.LANCZOS)
      square = Image.new("RGBA", self.THUMB_SIZE, (30, 30, 50, 255))
      offset = ((self.THUMB_SIZE[0] - img.width) // 2, (self.THUMB_SIZE[1] - img.height) // 2)
      square.paste(img, offset)
      square.save(cache_path, "PNG")
      return True
    except Exception:
      return False

  def load_photo(self, release_id: int) -> ImageTk.PhotoImage | None:
    if not self._pil_available:
      return None
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
    self._photo_cache.clear()
    self._preview_cache.clear()
    self._popup_cache.clear()
    self._placeholder = None

  def _get_popup_cache_path(self, release_id: int) -> Path:
    return self.cache_dir / f"{release_id}_popup.png"

  def load_popup_image(
    self, release_id: int, cover_url: str = None, headers: dict = None
  ) -> ImageTk.PhotoImage | None:
    if not self._pil_available:
      return None
    cached = self._popup_cache.get(release_id)
    if cached:
      return cached
    popup_path = self._get_popup_cache_path(release_id)
    photo = self._load_image_from_path(popup_path, release_id, cache_type="_popup_cache")
    if photo:
      return photo
    photo = self._download_and_cache_popup_image(release_id, cover_url, headers, popup_path)
    if photo:
      return photo
    preview_img = self.load_preview(release_id, cover_url, headers)
    if preview_img:
      return preview_img
    return None

  def _load_image_from_path(self, path: Path, release_id: int, cache_type: str) -> ImageTk.PhotoImage | None:
    if path.exists():
      try:
        from PIL import Image, ImageTk

        img = Image.open(path)
        photo = ImageTk.PhotoImage(img)
        getattr(self, cache_type)[release_id] = photo
        return photo
      except Exception:
        return None
    return None

  def _download_and_cache_popup_image(
    self, release_id: int, cover_url: str, headers: dict, popup_path: Path
  ) -> ImageTk.PhotoImage | None:
    if not headers or not release_id:
      return None
    try:
      import requests
      from io import BytesIO

      from PIL import Image, ImageTk

      image_url = cover_url
      if _is_low_quality_discogs_url(cover_url):
        hires_url = _fetch_hires_image_url(release_id, headers)
        if hires_url:
          image_url = hires_url
      if image_url:
        resp = requests.get(image_url, headers=headers, timeout=10)
        if resp.status_code == 200:
          img = Image.open(BytesIO(resp.content))
          img = img.convert("RGBA")
          img.thumbnail(self.POPUP_SIZE, Image.Resampling.LANCZOS)
          square = Image.new("RGBA", self.POPUP_SIZE, (30, 30, 50, 255))
          offset = ((self.POPUP_SIZE[0] - img.width) // 2, (self.POPUP_SIZE[1] - img.height) // 2)
          square.paste(img, offset)
          square.save(popup_path, "PNG")
          photo = ImageTk.PhotoImage(square)
          self._popup_cache[release_id] = photo
          return photo
    except Exception:
      return None
    return None

  def load_preview(
    self, release_id: int, cover_url: str = None, headers: dict = None
  ) -> ImageTk.PhotoImage | None:
    if not self._pil_available:
      return None
    cached = self._preview_cache.get(release_id)
    if cached:
      return cached
    preview_path = self._get_cache_path(release_id, preview=True)
    photo = self._load_preview_from_disk(preview_path, release_id)
    if photo:
      return photo
    photo = self._download_and_cache_preview(release_id, cover_url, headers, preview_path)
    if photo:
      return photo
    small_path = self._get_cache_path(release_id, preview=False)
    photo = self._upscale_small_thumbnail(small_path, release_id)
    if photo:
      return photo
    return None

  def _load_preview_from_disk(self, preview_path: Path, release_id: int) -> ImageTk.PhotoImage | None:
    if preview_path.exists():
      try:
        from PIL import Image, ImageTk

        img = Image.open(preview_path)
        photo = ImageTk.PhotoImage(img)
        self._preview_cache[release_id] = photo
        return photo
      except Exception:
        return None
    return None

  def _download_and_cache_preview(
    self, release_id: int, cover_url: str, headers: dict, preview_path: Path
  ) -> ImageTk.PhotoImage | None:
    if not headers or not release_id:
      return None
    try:
      import requests
      from io import BytesIO

      from PIL import Image, ImageTk

      image_url = cover_url
      if _is_low_quality_discogs_url(cover_url):
        hires_url = _fetch_hires_image_url(release_id, headers)
        if hires_url:
          image_url = hires_url
      if image_url:
        resp = requests.get(image_url, headers=headers, timeout=5)
        if resp.status_code == 200:
          img = Image.open(BytesIO(resp.content))
          img = img.convert("RGBA")
          img.thumbnail(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
          square = Image.new("RGBA", self.PREVIEW_SIZE, (30, 30, 50, 255))
          offset = ((self.PREVIEW_SIZE[0] - img.width) // 2, (self.PREVIEW_SIZE[1] - img.height) // 2)
          square.paste(img, offset)
          square.save(preview_path, "PNG")
          photo = ImageTk.PhotoImage(square)
          self._preview_cache[release_id] = photo
          return photo
    except Exception:
      return None
    return None

  def _upscale_small_thumbnail(self, small_path: Path, release_id: int) -> ImageTk.PhotoImage | None:
    if small_path.exists():
      try:
        from PIL import Image, ImageTk

        img = Image.open(small_path)
        img = img.resize(self.PREVIEW_SIZE, Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self._preview_cache[release_id] = photo
        return photo
      except Exception:
        return None
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
    if not self.cache.is_available():
      return
    if self._hide_job:
      self.parent.after_cancel(self._hide_job)
      self._hide_job = None
    if self.popup and self.current_release_id == release_id:
      self._position_popup(x, y)
      return
    photo = self.cache.load_preview(release_id, thumb_url, headers)
    if not photo:
      return
    self.current_release_id = release_id
    if not self.popup:
      self.popup = tk.Toplevel(self.parent)
      self.popup.wm_overrideredirect(True)
      self.popup.wm_attributes("-topmost", True)
      frame = tk.Frame(self.popup, bg="#1a1a2e", bd=2, relief="solid")
      frame.pack(fill="both", expand=True)
      self.label = tk.Label(frame, bg="#1a1a2e")
      self.label.pack(padx=2, pady=2)
    self.label.config(image=photo)
    self.label.image = photo
    self._position_popup(x, y)
    self.popup.deiconify()

  def _position_popup(self, x: int, y: int) -> None:
    if not self.popup:
      return
    offset_x = 20
    offset_y = -100
    screen_w = self.parent.winfo_screenwidth()
    screen_h = self.parent.winfo_screenheight()
    popup_w = self.cache.PREVIEW_SIZE[0] + 8
    popup_h = self.cache.PREVIEW_SIZE[1] + 8
    pos_x = x + offset_x
    pos_y = y + offset_y
    if pos_x + popup_w > screen_w:
      pos_x = x - popup_w - 10
    if pos_y + popup_h > screen_h:
      pos_y = screen_h - popup_h - 10
    if pos_y < 0:
      pos_y = 10
    self.popup.wm_geometry(f"+{pos_x}+{pos_y}")

  def hide(self, delay: int = 100) -> None:
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
    if self.popup:
      self.popup.destroy()
      self.popup = None
      self.label = None
