"""
Discogs OAuth 1.0a flow for user sign-in.

Runs the 3-legged OAuth flow with a local callback server.
Consumer key/secret from DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET (env or .env).
"""

from __future__ import annotations

import os
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    from requests_oauthlib import OAuth1Session
except ImportError:
    OAuth1Session = None  # type: ignore

API_BASE = "https://api.discogs.com"
OAUTH_REQUEST_URL = f"{API_BASE}/oauth/request_token"
OAUTH_ACCESS_URL = f"{API_BASE}/oauth/access_token"
OAUTH_AUTHORIZE_URL = "https://www.discogs.com/oauth/authorize"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/callback"


def _get_consumer_credentials(config: Optional[dict] = None) -> Optional[Tuple[str, str]]:
    """Get consumer key and secret from config or environment."""
    key = None
    secret = None
    if config:
        key = config.get("consumer_key") or config.get("consumer_key_encrypted")
        secret = config.get("consumer_secret") or config.get("consumer_secret_encrypted")
    if not key:
        key = os.environ.get("DISCOGS_CONSUMER_KEY")
    if not secret:
        secret = os.environ.get("DISCOGS_CONSUMER_SECRET")
    if key and secret:
        return (key.strip(), secret.strip())
    return None


def run_oauth_flow(
    consumer_key: str,
    consumer_secret: str,
    user_agent: str,
    callback_port: int = CALLBACK_PORT,
) -> Tuple[str, str]:
    """
    Run the OAuth 1.0a flow and return (access_token, access_token_secret).

    Opens browser for user to authorize, runs a local server to receive the callback.
    """
    if OAuth1Session is None:
        raise RuntimeError(
            "requests-oauthlib is required for OAuth sign-in. "
            "Install with: pip install requests-oauthlib"
        )

    callback_url = f"http://127.0.0.1:{callback_port}{CALLBACK_PATH}"
    verifier_received = threading.Event()
    verifier_value: list = []  # Use list to capture in closure
    request_token: Optional[str] = None
    request_token_secret: Optional[str] = None

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith(CALLBACK_PATH):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                verifier = (params.get("oauth_verifier") or [None])[0]
                if verifier:
                    verifier_value.append(verifier)
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Sign-in complete!</h2>"
                    b"<p>You can close this tab and return to the app.</p></body></html>"
                )
                verifier_received.set()

        def log_message(self, format, *args):
            pass  # Suppress server logs

    oauth = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        callback_uri=callback_url,
    )
    oauth.headers["User-Agent"] = user_agent

    # Step 1: Get request token
    resp = oauth.fetch_request_token(
        OAUTH_REQUEST_URL,
        allow_redirects=False,
    )
    request_token = resp.get("oauth_token")
    request_token_secret = resp.get("oauth_token_secret")
    if not request_token or not request_token_secret:
        raise RuntimeError("Discogs OAuth: failed to get request token")

    # Step 2: Authorization URL for user
    auth_url = oauth.authorization_url(OAUTH_AUTHORIZE_URL)

    # Step 3: Start local server and open browser
    server = HTTPServer(("127.0.0.1", callback_port), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.daemon = True
    server_thread.start()

    webbrowser.open(auth_url)

    # Wait for callback (with timeout)
    verifier_received.wait(timeout=120)
    server.server_close()

    if not verifier_value:
        raise RuntimeError("OAuth cancelled or timed out. No verification code received.")

    verifier = verifier_value[0]

    # Step 4: Exchange for access token
    oauth = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=request_token,
        resource_owner_secret=request_token_secret,
        verifier=verifier,
    )
    oauth.headers["User-Agent"] = user_agent

    token_resp = oauth.fetch_access_token(OAUTH_ACCESS_URL, allow_redirects=False)
    access_token = token_resp.get("oauth_token")
    access_secret = token_resp.get("oauth_token_secret")
    if not access_token or not access_secret:
        raise RuntimeError("Discogs OAuth: failed to get access token")

    return (access_token, access_secret)


def get_oauth_session(
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
    user_agent: str,
) -> "OAuth1Session":
    """Create an OAuth1Session for making authenticated API requests."""
    if OAuth1Session is None:
        raise RuntimeError("requests-oauthlib is required")
    session = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )
    session.headers["User-Agent"] = user_agent
    session.headers["Accept"] = "application/json"
    return session
