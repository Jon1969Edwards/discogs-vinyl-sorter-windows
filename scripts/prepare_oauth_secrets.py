#!/usr/bin/env python3
"""Write core/discogs_oauth_secrets.py from environment (CI release builds)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "core" / "discogs_oauth_secrets.py"


def main() -> int:
    key = os.environ.get("DISCOGS_CONSUMER_KEY", "").strip()
    secret = os.environ.get("DISCOGS_CONSUMER_SECRET", "").strip()
    if not key or not secret:
        print("Set DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET", file=sys.stderr)
        return 1
    OUT.write_text(
        f'''"""Bundled OAuth credentials (generated at build time — do not commit)."""
from __future__ import annotations

BUNDLED_DISCOGS_CONSUMER_KEY: str = {key!r}
BUNDLED_DISCOGS_CONSUMER_SECRET: str = {secret!r}
''',
        encoding="utf-8",
    )
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
