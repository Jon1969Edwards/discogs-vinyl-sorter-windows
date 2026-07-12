"""
Background/service layer for the Auto-Sort GUI.

Contains the non-UI logic for building the shelf order: configuration,
the local collection/price cache, authentication, collection fetching,
price handling, and the top-level build_once orchestration.

Kept free of any Tkinter/CustomTkinter dependencies so it can be reused
and tested independently of the GUI.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from core.api import (
    API_BASE,
    api_get,
    discogs_headers,
    fetch_prices_for_rows,
    get_identity,
)
from core.export import generate_txt_lines
from core.models import BuildResult
from core.oauth_discogs import get_oauth_session, _get_consumer_credentials
from core.paths import project_root
from core.sorting import collect_all_rows, sort_rows

# Collection cache file
CACHE_FILE = project_root() / ".discogs_collection_cache.json"
PRICE_CACHE_MAX_AGE_SECONDS = 86400 * 7  # 7 days before prices are considered stale


@dataclass
class AutoConfig:
  token: str
  user_agent: str
  output_dir: str
  per_page: int
  write_json: bool
  poll_seconds: int
  show_prices: bool = False
  currency: str = "USD"
  sort_by: str = "artist"
  oauth_access_token: str | None = None
  oauth_access_secret: str | None = None


class CollectionCache:
  """Local cache for Discogs collection data and prices.

  Stores:
  - Release info (artist, title, year, label, etc.)
  - Price info with timestamp
  - Avoids re-fetching unchanged releases
  """

  def __init__(self, cache_file: Path = CACHE_FILE):
    self.cache_file = cache_file
    self._data: dict = {
      "version": 1,
      "username": None,
      "releases": {},  # keyed by release_id
      "last_full_fetch": None,
    }
    self._load()

  def _load(self) -> None:
    """Load cache from disk."""
    try:
      if self.cache_file.exists():
        with self.cache_file.open("r", encoding="utf-8") as f:
          loaded = json.load(f)
          if loaded.get("version") == 1:
            self._data = loaded
    except Exception:
      pass

  def _save(self) -> None:
    """Save cache to disk."""
    try:
      with self.cache_file.open("w", encoding="utf-8") as f:
        json.dump(self._data, f, indent=2)
    except Exception:
      pass

  def get_username(self) -> str | None:
    """Get cached username."""
    return self._data.get("username")

  def set_username(self, username: str) -> None:
    """Set username and clear cache if changed."""
    if self._data.get("username") != username:
      # Different user - clear the cache
      self._data = {
        "version": 1,
        "username": username,
        "releases": {},
        "last_full_fetch": None,
      }
      self._save()

  def get_release(self, release_id: int) -> dict | None:
    """Get cached release data."""
    return self._data["releases"].get(str(release_id))

  def set_release(self, release_id: int, data: dict) -> None:
    """Cache a release's data."""
    self._data["releases"][str(release_id)] = {
      **data,
      "cached_at": time.time(),
    }

  def get_price(self, release_id: int, currency: str) -> tuple[float | None, int | None, bool]:
    """Get cached price info for a release.

    Returns: (lowest_price, num_for_sale, is_stale)
    """
    release = self._data["releases"].get(str(release_id))
    if not release:
      return None, None, True

    prices = release.get("prices", {})
    price_data = prices.get(currency)
    if not price_data:
      return None, None, True

    # Check if price is stale
    price_time = price_data.get("fetched_at", 0)
    is_stale = (time.time() - price_time) > PRICE_CACHE_MAX_AGE_SECONDS

    return price_data.get("lowest_price"), price_data.get("num_for_sale"), is_stale

  def set_price(self, release_id: int, currency: str, lowest_price: float | None, num_for_sale: int | None) -> None:
    """Cache price info for a release."""
    release_key = str(release_id)
    if release_key not in self._data["releases"]:
      self._data["releases"][release_key] = {"cached_at": time.time()}

    if "prices" not in self._data["releases"][release_key]:
      self._data["releases"][release_key]["prices"] = {}

    self._data["releases"][release_key]["prices"][currency] = {
      "lowest_price": lowest_price,
      "num_for_sale": num_for_sale,
      "fetched_at": time.time(),
    }

  def has_all_releases(self, release_ids: list[int]) -> bool:
    """Check if we have cached data for all given release IDs."""
    for rid in release_ids:
      if str(rid) not in self._data["releases"]:
        return False
    return True

  def get_cached_count(self) -> int:
    """Get number of cached releases."""
    return len(self._data["releases"])

  def get_prices_needing_fetch(self, release_ids: list[int], currency: str) -> list[int]:
    """Get release IDs that need price fetching (missing or stale)."""
    need_fetch = []
    for rid in release_ids:
      _, _, is_stale = self.get_price(rid, currency)
      if is_stale:
        need_fetch.append(rid)
    return need_fetch

  def save(self) -> None:
    """Explicitly save cache to disk."""
    self._save()

  def clear_prices(self, currency: str = None) -> int:
    """Clear cached prices, forcing re-fetch.

    Args:
      currency: If specified, only clear prices for this currency.
                If None, clear all prices.

    Returns:
      Number of releases affected.
    """
    count = 0
    for release_key, release_data in self._data["releases"].items():
      if "prices" in release_data:
        if currency:
          if currency in release_data["prices"]:
            del release_data["prices"][currency]
            count += 1
        else:
          release_data["prices"] = {}
          count += 1
    self._save()
    return count

  def clear(self) -> None:
    """Clear all cached data."""
    self._data = {
      "version": 1,
      "username": None,
      "releases": {},
      "last_full_fetch": None,
    }
    self._save()


def get_collection_count(headers: dict | None = None, username: str = "", session=None) -> int:
  """Fetch collection size cheaply via pagination metadata. Use headers or session."""
  url = f"{API_BASE}/users/{username}/collection/folders/0/releases"
  data = api_get(url, headers=headers, session=session, params={"page": "1", "per_page": "1"}).json()
  return int(data.get("pagination", {}).get("items", 0))


def build_once(cfg: AutoConfig, log: callable, progress_callback: callable = None, cache: CollectionCache = None, main_progress_q=None) -> BuildResult:
  """Build the shelf order once, with granular progress updates."""

  def report(action, message, fraction=None):
    if main_progress_q:
      main_progress_q.put((action, message, fraction))

  def get_headers_and_username():
    report("update", "Connecting to Discogs…", 0.03)
    try:
      _, headers, session, username = _get_user_headers(cfg, log)
      if cache:
        cache.set_username(username)
      return headers, session, username
    except Exception as e:
      report("error", f"Failed to get user headers: {e}")
      raise

  def collect_rows(headers, session, username):
    report("update", "Starting collection download…", 0.05)

    def on_page(page: int, total_pages: int, items_so_far: int) -> None:
      fraction = 0.08 + (0.72 * page / max(total_pages, 1))
      report(
        "update",
        f"Fetching collection… page {page} of {total_pages} ({items_so_far} items)",
        fraction,
      )

    try:
      rows = _collect_rows(cfg, headers, session, username, on_page=on_page)
      if not rows:
        log("No matching items found.")
        report("error", "No matching items found.")
        return []
      return rows
    except Exception as e:
      report("error", f"Failed to collect rows: {e}")
      raise

  def handle_prices_if_needed(headers, session, rows):
    from core.feature_gate import can_fetch_prices

    want_prices = cfg.show_prices or cfg.sort_by in ("price_asc", "price_desc")
    need_prices = want_prices and can_fetch_prices()
    report("update", "Checking if price data is needed…", 0.82)
    if want_prices and not can_fetch_prices():
      log("Marketplace prices require Pro. Prices disabled for this build.")
    if need_prices:
      report("update", "Fetching album prices from Discogs Marketplace…", 0.84)
      try:
        _handle_prices(cfg, log, progress_callback, cache, headers, session, rows, main_progress_q)
      except Exception as e:
        report("error", f"Failed to fetch prices: {e}")
        raise
    return need_prices

  def sort_and_generate_output(rows, need_prices, username):
    try:
      report("update", f"Sorting {len(rows)} releases…", 0.9)
      rows_sorted = sort_rows(rows, "normal", sort_by=cfg.sort_by)
      report("update", "Preparing shelf order…", 0.96)
      lines = generate_txt_lines(rows_sorted, dividers=False, align=False, show_country=False, show_price=need_prices)
      report("done", "Done!", 1.0)
      return BuildResult(username=username, rows_sorted=rows_sorted, lines=lines)
    except Exception as e:
      report("error", f"Build failed: {e}")
      raise

  def ensure_output_dir_exists(path):
    out_dir = Path(path)
    out_dir.mkdir(parents=True, exist_ok=True)

  ensure_output_dir_exists(cfg.output_dir)
  headers, session, username = get_headers_and_username()
  rows = collect_rows(headers, session, username)
  if not rows:
    return BuildResult(username=username, rows_sorted=[], lines=[])
  need_prices = handle_prices_if_needed(headers, session, rows)
  return sort_and_generate_output(rows, need_prices, username)


def _get_user_headers(cfg: AutoConfig, log: callable):
    """Return (token, headers, session, username). Use OAuth if available, else token."""
    if cfg.oauth_access_token and cfg.oauth_access_secret:
        creds = _get_consumer_credentials(None)
        if not creds:
            raise RuntimeError(
                "Discogs sign-in is saved but this build is missing OAuth credentials. "
                "Reinstall from the official installer or sign in again."
            )
        consumer_key, consumer_secret = creds
        try:
            session = get_oauth_session(
                consumer_key, consumer_secret,
                cfg.oauth_access_token, cfg.oauth_access_secret,
                cfg.user_agent,
            )
            ident = get_identity(session=session)
            username = ident.get("username")
            if username:
                log(f"User: {username} (signed in)")
                return None, None, session, username
            raise RuntimeError("Discogs did not return a username for this sign-in.")
        except Exception as e:
            raise RuntimeError(f"Discogs sign-in failed: {e}") from e
    token = (cfg.token or "").strip() or os.getenv("DISCOGS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Could not connect to Discogs. Sign in again with Discogs in Settings, "
            "or set a personal access token."
        )
    headers = discogs_headers(token, cfg.user_agent)
    ident = get_identity(headers=headers)
    username = ident.get("username")
    if not username:
        raise RuntimeError("Could not determine username from token.")
    log(f"User: {username}")
    return token, headers, None, username


def _collect_rows(cfg: AutoConfig, headers: dict | None, session, username: str, on_page=None):
    return collect_all_rows(
        headers=headers,
        username=username,
        session=session,
        per_page=max(1, min(int(cfg.per_page), 100)),
        max_pages=None,
        extra_articles=[],
        last_name_first=True,
        lnf_allow_3=False,
        lnf_exclude=set(),
        lnf_safe_bands=True,
        on_page=on_page,
    )


def _handle_prices(cfg, log, progress_callback, cache, headers, session, rows, main_progress_q=None):
  releases_needing_fetch, cached_count = _populate_prices_from_cache(cfg, cache, rows)
  if cached_count > 0:
    log(f"Loaded {cached_count} prices from cache.")
  if releases_needing_fetch:
    _fetch_and_cache_prices(cfg, log, progress_callback, cache, headers, session, releases_needing_fetch, cached_count, main_progress_q)
  else:
    log("All prices loaded from cache.")
    if main_progress_q:
      main_progress_q.put(("update", "All prices loaded from cache."))


def _populate_prices_from_cache(cfg, cache, rows):
    releases_needing_fetch = []
    cached_count = 0
    if cache:
        for row in rows:
            if row.release_id:
                lowest, num_for_sale, is_stale = cache.get_price(row.release_id, cfg.currency)
                if not is_stale:
                    row.lowest_price = lowest
                    row.median_price = lowest
                    row.num_for_sale = num_for_sale
                    row.price_currency = cfg.currency
                    cached_count += 1
                else:
                    releases_needing_fetch.append(row)
            else:
                releases_needing_fetch.append(row)
    else:
        releases_needing_fetch = [r for r in rows if r.release_id]
    return releases_needing_fetch, cached_count


def _fetch_and_cache_prices(cfg, log, progress_callback, cache, headers, session, releases_needing_fetch, cached_count, main_progress_q=None):
    def _report_progress(action, message, fraction=None):
        if progress_callback:
            progress_callback(action, message, fraction)
        elif main_progress_q:
            main_progress_q.put((action, message, fraction))

    def _cache_row(row) -> None:
        if not cache or not row.release_id:
            return
        cache.set_price(row.release_id, cfg.currency, row.lowest_price, row.num_for_sale)

    def _fetch_prices():
        total_to_fetch = len({r.release_id for r in releases_needing_fetch if r.release_id})
        log(f"Fetching {total_to_fetch} prices ({cfg.currency})...")
        _report_progress("show", f"Fetching {total_to_fetch} album prices in {cfg.currency}.\n({cached_count} loaded from cache)")
        _report_progress("update", f"Fetching {total_to_fetch} album prices in {cfg.currency}...")
        fetched_since_save = 0

        def price_progress(msg: str):
            log(msg)
            _report_progress("update", msg)

        def on_price_fetched(row) -> None:
            nonlocal fetched_since_save
            _cache_row(row)
            fetched_since_save += 1
            if cache and fetched_since_save >= 10:
                cache.save()
                fetched_since_save = 0

        try:
            fetch_prices_for_rows(
                headers=headers,
                session=session,
                rows=releases_needing_fetch,
                currency=cfg.currency,
                log_callback=price_progress,
                debug=False,
                on_price_fetched=on_price_fetched,
            )
        except Exception as e:
            _report_progress("error", f"Price fetch failed: {e}")
            raise

    _fetch_prices()
    if cache:
        cache.save()
    log("Price fetch complete.")
    _report_progress("update", "Price fetch complete.")
    _report_progress("close", None)
