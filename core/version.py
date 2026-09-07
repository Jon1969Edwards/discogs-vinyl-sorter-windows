"""Application name and version (single source of truth)."""

from __future__ import annotations

APP_NAME = "Spindle"
APP_SLUG = "spindle"
__version__ = "1.0.0"

# Public GitHub repository (raw + releases)
GITHUB_OWNER = "Jon1969Edwards"
GITHUB_REPO = "discogs-vinyl-sorter-windows"
GITHUB_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"{GITHUB_URL}/releases/latest"

# Update check: raw URL to version.json on the default branch
UPDATE_MANIFEST_URL = (
  f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/release/version.json"
)

SUPPORT_EMAIL = "jon1969edwards@gmail.com"

# Lemon Squeezy / Gumroad checkout. Override at release bake with SPINDLE_PURCHASE_URL
# (see docs/RELEASE.md). Until the store product exists, keep this as Releases so
# purchase_store_ready() stays False and Buy Pro is hidden.
PURCHASE_URL = GITHUB_RELEASES_URL

FEEDBACK_MAILTO = f"mailto:{SUPPORT_EMAIL}?subject={APP_NAME}%20Feedback"

DISCOGS_DISCLAIMER = "Not affiliated with Discogs."


def purchase_store_ready() -> bool:
    """True when Buy Pro should open a real checkout (not GitHub Releases)."""
    url = (PURCHASE_URL or "").strip()
    if not url:
        return False
    if url.rstrip("/") == GITHUB_RELEASES_URL.rstrip("/"):
        return False
    return True
