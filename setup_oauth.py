#!/usr/bin/env python3
"""One-time developer setup for bundled Discogs OAuth sign-in."""

from __future__ import annotations

import webbrowser

from core.oauth_discogs import (
    CALLBACK_PATH,
    CALLBACK_PORT,
    _get_consumer_credentials,
    save_consumer_credentials,
)

DEVELOPERS_URL = "https://www.discogs.com/settings/developers"
CALLBACK_URL = f"http://127.0.0.1:{CALLBACK_PORT}{CALLBACK_PATH}"


def main() -> None:
    print()
    print("=" * 56)
    print("Spindle — one-time OAuth setup")
    print("=" * 56)
    print()
    print("This is a ONE-TIME step for whoever builds or distributes the app.")
    print("After this, users only click \"Sign in with Discogs\" in the app.")
    print()

    if _get_consumer_credentials():
        answer = input("OAuth credentials already exist. Replace them? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Keeping existing credentials.")
            return

    print("1. Your browser will open Discogs → Settings → Developers.")
    print("2. Create an application (or open an existing one).")
    print(f"3. Set the callback URL to: {CALLBACK_URL}")
    print("4. Copy the Consumer Key and Consumer Secret back here.")
    print()
    input("Press Enter to open Discogs Developers… ")
    webbrowser.open(DEVELOPERS_URL)
    print()

    key = input("Consumer Key: ").strip()
    secret = input("Consumer Secret: ").strip()
    if not key or not secret:
        print("ERROR: Both values are required.")
        raise SystemExit(1)

    save_consumer_credentials(key, secret)
    print()
    print("Saved to core/discogs_oauth_secrets.py")
    print("Sign in with Discogs is now enabled for this build.")
    print("Restart the app, then click \"Sign in with Discogs\".")
    print()


if __name__ == "__main__":
    main()
