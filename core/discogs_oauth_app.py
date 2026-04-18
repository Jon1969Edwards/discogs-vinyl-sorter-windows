"""
Bundled Discogs OAuth consumer key and secret (optional).

For a public GitHub repo: leave BUNDLED_* empty and use a local .env (gitignored)
with DISCOGS_CONSUMER_KEY / DISCOGS_CONSUMER_SECRET, or core/discogs_oauth_secrets.py
(copy from discogs_oauth_secrets.example.py; that file is gitignored). Do not commit
real keys in this file.

If you distribute a private build or installer where embedding keys is acceptable,
register one app at https://www.discogs.com/settings/developers with callback:

    http://127.0.0.1:8765/callback

Environment variables still override these when both are set.
"""

from __future__ import annotations

# Safe default for GitHub: empty; OAuth uses .env or discogs_oauth_secrets.py locally.
BUNDLED_DISCOGS_CONSUMER_KEY: str = ""
BUNDLED_DISCOGS_CONSUMER_SECRET: str = ""
