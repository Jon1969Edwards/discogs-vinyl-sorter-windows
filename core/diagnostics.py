"""Export redacted diagnostics for support."""

from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.config_store import load_config
from core.paths import project_root
from core.version import APP_NAME, __version__


def _redact_config(cfg: dict) -> dict:
    out = dict(cfg)
    for key in list(out.keys()):
        if "token" in key.lower() or "secret" in key.lower() or key == "license":
            out[key] = "[REDACTED]"
    return out


def export_diagnostics_zip(dest: Path | None = None) -> Path:
    root = project_root()
    dest = dest or (root / f"diagnostics_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip")
    info = {
        "app": APP_NAME,
        "version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "frozen": getattr(sys, "frozen", False),
    }
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system.json", json.dumps(info, indent=2))
        zf.writestr("config_redacted.json", json.dumps(_redact_config(load_config()), indent=2))
        log_path = root / "crash.log"
        if log_path.exists():
            zf.write(log_path, arcname="crash.log")
    return dest
