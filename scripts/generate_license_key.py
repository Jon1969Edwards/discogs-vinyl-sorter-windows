#!/usr/bin/env python3
"""Generate a Pro license key for beta testers or manual sales."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.licensing import generate_license_key


def main() -> int:
    p = argparse.ArgumentParser(description="Generate Spindle Pro license key")
    p.add_argument("--email", default="", help="Optional purchaser email embedded in key")
    args = p.parse_args()
    try:
        print(generate_license_key(email=args.email))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Example (PowerShell): $env:VSS_LICENSE_SECRET='your-long-random-secret'",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
