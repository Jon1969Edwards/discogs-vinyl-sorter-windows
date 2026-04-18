"""
Bundled Discogs OAuth consumer key and secret (optional).

Discogs requires a registered application for OAuth. If you ship this app to end
users who should only click "Sign in" (no .env), register one application at
https://www.discogs.com/settings/developers with callback URL:

    http://127.0.0.1:8765/callback

Then paste the Consumer Key and Consumer Secret below. One registration serves
all users of your build.

DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET in the environment still
override these when both are set (for developers).
"""

from __future__ import annotations

# Leave empty to rely on environment variables only; fill for zero-config sign-in.
BUNDLED_DISCOGS_CONSUMER_KEY: str = ""
BUNDLED_DISCOGS_CONSUMER_SECRET: str = ""
