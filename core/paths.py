"""Filesystem roots for app files and local user data.

- ``project_root()``: repo root (dev) or folder containing the ``.exe`` (frozen).
  Used for ``.env``, bundled docs, and OAuth secret modules.
- ``user_data_dir()``: per-user local data (covers, wishlist, config, caches).
  On Windows: ``%LOCALAPPDATA%\\Spindle``. Never committed to git.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from core.version import APP_SLUG


def project_root() -> Path:
  """Directory containing `autosort_gui.py` / `discogs_app.py`, or the built `.exe`."""
  if getattr(sys, "frozen", False) and getattr(sys, "executable", None):
    return Path(sys.executable).resolve().parent
  return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
  """Per-user directory for Spindle config, caches, and album artwork."""
  if sys.platform == "win32":
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
  elif sys.platform == "darwin":
    root = Path.home() / "Library" / "Application Support"
  else:
    root = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
  path = root / APP_SLUG.capitalize()  # Spindle
  path.mkdir(parents=True, exist_ok=True)
  return path


def _legacy_project_path(name: str) -> Path:
  return project_root() / name


def migrate_user_file(filename: str, *, legacy_names: tuple[str, ...] | None = None) -> Path:
  """Return path under user_data_dir, copying from project_root if needed."""
  dest = user_data_dir() / filename
  if dest.exists():
    return dest
  candidates = list(legacy_names or ()) + [filename]
  seen: set[Path] = set()
  for name in candidates:
    src = _legacy_project_path(name)
    if src in seen:
      continue
    seen.add(src)
    if src.exists() and src.is_file():
      try:
        shutil.copy2(src, dest)
      except OSError:
        pass
      break
  return dest


def migrate_user_dir(dirname: str, *, legacy_names: tuple[str, ...] | None = None) -> Path:
  """Return directory under user_data_dir, copying from project_root if needed."""
  dest = user_data_dir() / dirname
  dest.mkdir(parents=True, exist_ok=True)
  if any(dest.iterdir()):
    return dest
  candidates = list(legacy_names or ()) + [dirname]
  seen: set[Path] = set()
  for name in candidates:
    src = _legacy_project_path(name)
    if src in seen:
      continue
    seen.add(src)
    if src.exists() and src.is_dir():
      try:
        for item in src.iterdir():
          target = dest / item.name
          if item.is_file() and not target.exists():
            shutil.copy2(item, target)
          elif item.is_dir() and not target.exists():
            shutil.copytree(item, target)
      except OSError:
        pass
      break
  return dest
