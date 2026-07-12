"""Check for application updates."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Optional

from core.version import UPDATE_MANIFEST_URL, __version__


@dataclass
class UpdateInfo:
    latest_version: str
    download_url: str
    release_notes: str


def _parse_version(v: str) -> tuple:
    parts = []
    for piece in v.replace("-", ".").split("."):
        num = ""
        for ch in piece:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def check_for_update(timeout: float = 8.0) -> Optional[UpdateInfo]:
    try:
        req = urllib.request.Request(UPDATE_MANIFEST_URL, headers={"User-Agent": "Spindle"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        latest = data.get("version", "")
        if _parse_version(latest) <= _parse_version(__version__):
            return None
        return UpdateInfo(
            latest_version=latest,
            download_url=data.get("download_url", ""),
            release_notes=data.get("release_notes", ""),
        )
    except Exception:
        return None
