"""Filesystem root for config, .env, and caches.

In development this is the repository root. In a PyInstaller build it is the
folder containing the .exe (so .env lives next to the app, not inside the
bundled temp extract).
"""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
  """Directory containing `autosort_gui.py` / `discogs_app.py`, or the built `.exe`."""
  if getattr(sys, "frozen", False) and getattr(sys, "executable", None):
    return Path(sys.executable).resolve().parent
  return Path(__file__).resolve().parent.parent
