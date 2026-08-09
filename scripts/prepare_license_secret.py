#!/usr/bin/env python3
"""Write core/license_secrets.py from VSS_LICENSE_SECRET (CI release builds)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "core" / "license_secrets.py"


def main() -> int:
    secret = os.environ.get("VSS_LICENSE_SECRET", "").strip()
    if not secret:
        print("Set VSS_LICENSE_SECRET for release builds", file=sys.stderr)
        return 1
    if secret == "VSS-CHANGE-ME-IN-RELEASE-BUILDS-2026":
        print("Refusing to bake the public default license secret", file=sys.stderr)
        return 1
    OUT.write_text(
        f'''"""Bundled Pro license HMAC secret (generated at build time — do not commit)."""
from __future__ import annotations

BUNDLED_LICENSE_SECRET: str = {secret!r}
''',
        encoding="utf-8",
    )
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
