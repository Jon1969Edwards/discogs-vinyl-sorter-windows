"""Bundled Pro license HMAC secret (generated at build time — do not commit).

Copy from license_secrets.example.py for local layout reference.
Release CI runs scripts/prepare_license_secret.py with VSS_LICENSE_SECRET set.
"""

from __future__ import annotations

# Empty in the repo. Release builds replace this file.
BUNDLED_LICENSE_SECRET: str = ""
