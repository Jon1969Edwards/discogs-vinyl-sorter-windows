"""Export redacted diagnostics for support."""

from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.config_store import load_config
from core.paths import project_root, user_data_dir
from core.version import APP_NAME, __version__


def _redact_config(cfg: dict) -> dict:
    out = dict(cfg)
    for key in list(out.keys()):
        if "token" in key.lower() or "secret" in key.lower() or key == "license":
            out[key] = "[REDACTED]"
    return out


def export_diagnostics_zip(dest: Path | None = None) -> Path:
    data = user_data_dir()
    dest = dest or (data / f"diagnostics_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip")
    info = {
        "app": APP_NAME,
        "version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "frozen": getattr(sys, "frozen", False),
        "user_data_dir": str(data),
        "project_root": str(project_root()),
    }
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system.json", json.dumps(info, indent=2))
        zf.writestr("config_redacted.json", json.dumps(_redact_config(load_config()), indent=2))
        for log_path in (data / "crash.log", project_root() / "crash.log"):
            if log_path.exists():
                zf.write(log_path, arcname="crash.log")
                break
    return dest
