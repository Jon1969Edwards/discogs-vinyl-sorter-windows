"""Application name and version (single source of truth)."""

from __future__ import annotations

APP_NAME = "Spindle"
APP_SLUG = "spindle"
__version__ = "1.0.0-beta.1"

# Update check: raw URL to version.json on GitHub Releases or your CDN
UPDATE_MANIFEST_URL = (
  "https://raw.githubusercontent.com/your-org/discogs-vinyl-sorter-windows/main/release/version.json"
)

SUPPORT_EMAIL = "support@example.com"
PURCHASE_URL = "https://your-store.lemonsqueezy.com/buy/spindle-pro"
FEEDBACK_MAILTO = f"mailto:{SUPPORT_EMAIL}?subject={APP_NAME}%20Feedback"

DISCOGS_DISCLAIMER = "Not affiliated with Discogs."
