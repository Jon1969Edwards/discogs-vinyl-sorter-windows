"""
Discogs API operations module.

Handles all interactions with the Discogs API including:
- Token management and headers
- Retry logic and rate limiting
- Identity and collection fetching
- Marketplace price fetching
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    # Load .env if available, but don't require it
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

try:
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore

from core.models import ReleaseRow

API_BASE = "https://api.discogs.com"


def get_token(args_token: Optional[str]) -> str:
    """Get Discogs API token from args or environment."""
    token = args_token or os.getenv("DISCOGS_TOKEN")
    if not token:
        sys.exit(
            "Error: No token provided. Pass --token or set DISCOGS_TOKEN in the environment (optionally via .env)."
        )
    return token.strip()


def discogs_headers(token: str, user_agent: str) -> Dict[str, str]:
    """Build headers for Discogs API requests."""
    return {
        "Authorization": f"Discogs token={token}",
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


def _should_retry(status: int) -> bool:
    """Check if HTTP status code should trigger a retry."""
    return status == 429 or 500 <= status < 600


def _retry_sleep_seconds(resp: Any, attempt: int, backoff: float) -> float:
    """Calculate sleep time for retry based on response headers."""
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return min(backoff * (2 ** attempt), 10.0)


def _polite_rate_limit_pause(resp) -> None:
    """Pause if approaching Discogs rate limit."""
    try:
        remaining = int(resp.headers.get("X-Discogs-Ratelimit-Remaining", "5"))
        if remaining <= 1:
            time.sleep(2)
    except Exception:
        pass


def api_get(url: str, headers: Optional[Dict[str, str]] = None,
            session: Optional[Any] = None,
            params: Optional[Dict[str, str]] = None,
            retries: int = 3, backoff: float = 1.0):
    """Execute a GET request to Discogs API with retry logic.

    Use either headers (token auth) or session (OAuth). If both provided, session takes precedence.

    Returns:
        requests.Response object

    Raises:
        RuntimeError: If requests is not installed or if all retries fail
    """
    if requests is None:
        raise RuntimeError("Missing dependency 'requests'. Install requirements.txt (pip install -r requirements.txt).")
    if session is None and headers is None:
        raise ValueError("api_get requires either headers or session")
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            if session is not None:
                resp = session.get(url, params=params, timeout=30)
            else:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            status = resp.status_code
            if status < 400:
                _polite_rate_limit_pause(resp)
                return resp
            if _should_retry(status):
                time.sleep(_retry_sleep_seconds(resp, attempt, backoff))
                last_error = RuntimeError(f"Transient API error {status}")
                continue
            raise RuntimeError(f"Discogs API error {status}: {resp.text[:200]}")
        except Exception as e:
            # Only treat requests exceptions as retryable network errors.
            if requests is not None and isinstance(e, requests.RequestException):
                last_error = e
                time.sleep(min(backoff * (2 ** attempt), 10.0))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("Discogs API request failed after retries")


def get_identity(headers: Optional[Dict[str, str]] = None, session: Optional[Any] = None) -> Dict:
    """Get the authenticated user's identity from Discogs API. Use headers or session."""
    url = f"{API_BASE}/oauth/identity"
    return api_get(url, headers=headers, session=session).json()


def fetch_release_price(headers: Optional[Dict[str, str]] = None, release_id: int = 0,
                        currency: str = "USD", debug_log: Optional[callable] = None,
                        session: Optional[Any] = None) -> Tuple[Optional[float], Optional[int], str]:
    """Fetch the lowest price and number for sale for a release from Discogs Marketplace.

    Use headers (token auth) or session (OAuth). Returns (lowest_price, num_for_sale, actual_currency).
    """
    url = f"{API_BASE}/marketplace/stats/{release_id}"

    try:
        resp = api_get(url, headers=headers, session=session, params={"curr_abbr": currency})
        data = resp.json()

        if debug_log:
            debug_log(f"  API response for release {release_id}: {data}")

        # Check if blocked from sale
        if data.get("blocked_from_sale"):
            return (None, 0, currency)

        # num_for_sale tells us how many copies are available
        num_for_sale = data.get("num_for_sale")
        if num_for_sale is None or num_for_sale == 0:
            return (None, 0, currency)

        # Get lowest price from marketplace stats
        lowest_price_data = data.get("lowest_price")
        if lowest_price_data and isinstance(lowest_price_data, dict):
            lowest = lowest_price_data.get("value")
            # Use the actual currency from the response, not the requested one
            actual_currency = lowest_price_data.get("currency", currency)
            if debug_log and actual_currency != currency:
                debug_log(f"  WARNING: Requested {currency} but API returned {actual_currency}")
            lowest_float = float(lowest) if lowest is not None else None
            return (lowest_float, num_for_sale, actual_currency)
        else:
            return (None, num_for_sale, currency)
    except Exception as e:
        if debug_log:
            debug_log(f"  Error fetching price: {e}")
        return (None, None, currency)


def fetch_prices_for_rows(
    headers: Optional[Dict[str, str]] = None,
    rows: Optional[List["ReleaseRow"]] = None,
    currency: str = "USD",
    log_callback: Optional[callable] = None,
    debug: bool = False,
    session: Optional[Any] = None,
) -> None:
    """Fetch and populate price info for a list of ReleaseRows. Use headers or session."""
    # Cache by release_id to avoid duplicate fetches
    # Cache: release_id -> (lowest_price, num_for_sale, actual_currency)
    price_cache: Dict[int, Tuple[Optional[float], Optional[int], str]] = {}
    total = len([r for r in rows if r.release_id])
    fetched = 0

    # Debug logger if enabled
    debug_log = log_callback if debug else None

    for row in rows:
        if not row.release_id:
            continue
        rid = row.release_id
        if rid not in price_cache:
            fetched += 1
            if log_callback:
                # Show album being fetched and progress count
                album_info = f"{row.artist_display} - {row.title}"
                if len(album_info) > 40:
                    album_info = album_info[:37] + "..."
                log_callback(f"[{fetched}/{total}] {album_info}")
            price_cache[rid] = fetch_release_price(headers=headers, session=session, release_id=rid, currency=currency, debug_log=debug_log)
        lowest, num_for_sale, actual_currency = price_cache[rid]
        row.lowest_price = lowest
        row.median_price = lowest  # Using lowest as median approximation
        row.num_for_sale = num_for_sale
        row.price_currency = actual_currency  # Use actual currency from API


def iterate_collection(headers: Optional[Dict[str, str]] = None, username: str = "",
                       per_page: int = 100, max_pages: Optional[int] = None,
                       session: Optional[Any] = None) -> Iterable[Dict]:
    """Iterate through all releases in a user's collection. Use headers or session."""
    page = 1
    total_pages: Optional[int] = None
    while True:
        url = f"{API_BASE}/users/{username}/collection/folders/0/releases"
        params = {
            "page": str(page),
            "per_page": str(per_page),
            "sort": "artist",
            "sort_order": "asc",
        }
        data = api_get(url, headers=headers, session=session, params=params).json()
        if total_pages is None:
            total_pages = int(data.get("pagination", {}).get("pages", 1))
        for item in data.get("releases", []):
            yield item
        page += 1
        if max_pages and page > max_pages:
            break
        if total_pages and page > total_pages:
            break
