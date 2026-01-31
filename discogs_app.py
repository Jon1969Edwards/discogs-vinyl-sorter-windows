#!/usr/bin/env python3
"""
Discogs 33⅓ LP Shelf Sorter

Fetches your Discogs collection with a Personal Access Token, filters to
Vinyl LPs at 33⅓ RPM, normalizes artist/title for sorting (e.g., strips
leading articles and Discogs numeric suffixes like "(2)"), and outputs
both a printable shelf order (TXT) and a CSV.

Token discovery order:
- CLI: --token
- Environment: DISCOGS_TOKEN
- Optional .env file (if python-dotenv is installed)

Usage examples:
  python discogs_app.py --user-agent "VinylSorter/1.0 (you@example.com)"
  python discogs_app.py --various-policy last --articles-extra "le,la,les,el,los,las,der,die,das"
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass
from core.models import ReleaseRow
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Set

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


API_BASE = "https://api.discogs.com"
VERSION = "0.2.0"




def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Discogs LP shelf sorter")
  parser.add_argument(
    "--version",
    action="version",
    version=f"%(prog)s {VERSION}",
    help="Show program's version number and exit.",
  )
  parser.add_argument(
    "--token",
    help="Discogs Personal Access Token. If omitted, reads DISCOGS_TOKEN env var.",
  )
  parser.add_argument(
    "--user-agent",
    default="VinylSorter/1.0 (+contact)",
    help="User-Agent header per Discogs API policy (include a way to contact you).",
  )
  parser.add_argument(
    "--various-policy",
    choices=["normal", "last", "title"],
    default="normal",
    help="How to treat 'Various' artists when sorting: normal sort, push to end, or sort by title (so they file under the release title).",
  )
  parser.add_argument(
    "--articles-extra",
    default="",
    help="Comma-separated extra leading articles to strip for sorting (e.g., 'le,la,les,el,los,las,der,die,das').",
  )
  parser.add_argument(
    "--output-dir",
    default=".",
    help="Directory where outputs are written (vinyl_shelf_order.txt/.csv).",
  )
  parser.add_argument(
    "--dividers",
    action="store_true",
    help="Insert letter dividers (=== A ===) in the TXT output.",
  )
  parser.add_argument(
    "--json",
    action="store_true",
    help="Also write a JSON export (vinyl_shelf_order.json).",
  )
  parser.add_argument(
    "--include-45s",
    action="store_true",
    help="Additionally write outputs for 7\" 45 RPM vinyl singles (files: vinyl45_shelf_order.*).",
  )
  parser.add_argument(
    "--include-cds",
    action="store_true",
    help="Additionally write outputs for CDs (files: cd_shelf_order.*).",
  )
  parser.add_argument(
    "--valuable-sek",
    type=float,
    default=None,
    help="Emit a separate TXT listing items whose Discogs lowest_price is >= this threshold (SEK). Example: --valuable-sek 500",
  )
  parser.add_argument(
    "--last-name-first",
    action="store_true",
    help="Sort artists by last word of their name when heuristic applies (does not change display).",
  )
  parser.add_argument(
    "--lnf-safe-bands",
    action="store_true",
    help="When used with --last-name-first, avoid flipping obvious band-like two-word names (e.g., plural nouns, 'Orchestra', 'Trio').",
  )
  parser.add_argument(
    "--txt-align",
    action="store_true",
    help="Align artist and title columns in TXT output for easier scanning.",
  )
  parser.add_argument(
    "--show-country",
    action="store_true",
    help="Include country code at end of TXT lines if present.",
  )
  parser.add_argument(
    "--max-pages",
    type=int,
    default=None,
    help="Optional safety cap for number of collection pages to fetch.",
  )
  parser.add_argument(
    "--per-page",
    type=int,
    default=100,
    help="Items per page for API pagination (max 100).",
  )
  parser.add_argument(
    "--lp-strict",
    action="store_true",
    help="Require explicit 33 RPM in format descriptions (default: LP implies ~33 even if RPM missing).",
  )
  parser.add_argument(
    "--lp-probable-33",
    action="store_true",
    help="Treat LP/Album as 33 RPM unless descriptors explicitly show 45/78; safer than default but not as strict as --lp-strict.",
  )
  parser.add_argument(
    "--report-filters",
    action="store_true",
    help="When used with --lp-probable-33, write a report of LPs excluded due to explicit 45/78 descriptors.",
  )
  parser.add_argument(
    "--debug-stats",
    action="store_true",
    help="Print summary stats about how many items were filtered out by format checks.",
  )
  return parser.parse_args()


def get_token(args_token: Optional[str]) -> str:
  token = args_token or os.getenv("DISCOGS_TOKEN")
  if not token:
    sys.exit(
      "Error: No token provided. Pass --token or set DISCOGS_TOKEN in the environment (optionally via .env)."
    )
  return token.strip()


def discogs_headers(token: str, user_agent: str) -> Dict[str, str]:
  return {
    "Authorization": f"Discogs token={token}",
    "User-Agent": user_agent,
    "Accept": "application/json",
  }


def _should_retry(status: int) -> bool:
  return status == 429 or 500 <= status < 600


from typing import Any

def _retry_sleep_seconds(resp: Any, attempt: int, backoff: float) -> float:
  retry_after = resp.headers.get("Retry-After")
  if retry_after:
    try:
      return float(retry_after)
    except ValueError:
      pass
  return min(backoff * (2 ** attempt), 10.0)


def _polite_rate_limit_pause(resp) -> None:
  try:
    remaining = int(resp.headers.get("X-Discogs-Ratelimit-Remaining", "5"))
    if remaining <= 1:
      time.sleep(2)
  except Exception:
    pass


from requests import Response

def api_get(url: str, headers: Dict[str, str], params: Optional[Dict[str, str]] = None,
            retries: int = 3, backoff: float = 1.0) -> Response:
  if requests is None:
    raise RuntimeError("Missing dependency 'requests'. Install requirements.txt (pip install -r requirements.txt).")
  last_error: Optional[Exception] = None
  for attempt in range(retries):
    try:
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


def get_identity(headers: Dict[str, str]) -> Dict:
  url = f"{API_BASE}/oauth/identity"
  return api_get(url, headers).json()


def fetch_release_price(headers: Dict[str, str], release_id: int, currency: str = "USD", debug_log: Optional[callable] = None) -> Tuple[Optional[float], Optional[int], str]:
  """Fetch the lowest price and number for sale for a release from Discogs Marketplace.
  
  Returns (lowest_price, num_for_sale, actual_currency) tuple. Values are None if not available.
  Uses the Marketplace Statistics endpoint for accurate current pricing.
  
  Note: This fetches the price for the SPECIFIC pressing (release_id), not the master release.
  This gives the most accurate value for the user's exact record.
  """
  url = f"{API_BASE}/marketplace/stats/{release_id}"
  
  try:
    resp = api_get(url, headers, params={"curr_abbr": currency})
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
  headers: Dict[str, str],
  rows: List["ReleaseRow"],
  currency: str = "USD",
  log_callback: Optional[callable] = None,
  debug: bool = False,
) -> None:
  """Fetch and populate price info for a list of ReleaseRows in-place.
  
  This makes API calls for each unique release, so it can be slow for large collections.
  """
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
      price_cache[rid] = fetch_release_price(headers, rid, currency, debug_log=debug_log)
    lowest, num_for_sale, actual_currency = price_cache[rid]
    row.lowest_price = lowest
    row.median_price = lowest  # Using lowest as median approximation
    row.num_for_sale = num_for_sale
    row.price_currency = actual_currency  # Use actual currency from API


def iterate_collection(headers: Dict[str, str], username: str, per_page: int = 100, max_pages: Optional[int] = None) -> Iterable[Dict]:
  page = 1
  total_pages: Optional[int] = None
  while True:
    url = f"{API_BASE}/users/{username}/collection/folders/0/releases"
    params = {
      "page": str(page),
      "per_page": str(per_page),
      # Sort isn't critical since we post-process, but helps UX if interrupted
      "sort": "artist",
      "sort_order": "asc",
    }
    data = api_get(url, headers, params=params).json()
    if total_pages is None:
      total_pages = int(data.get("pagination", {}).get("pages", 1))
    for item in data.get("releases", []):
      yield item
    page += 1
    if max_pages and page > max_pages:
      break
    if total_pages and page > total_pages:
      break


def _desc_set_has_33rpm(descs: set[str]) -> bool:
  """Heuristic to decide if a set of format description tokens denotes 33 RPM.

  Accept if:
  - A token contains both '33' and 'rpm' (after removing dots/spaces), OR
  - There is at least one token containing '33' (including '33⅓', '33 1/3') AND either:
      * a separate token that normalizes to RPM, OR
      * a token containing 'lp' or 'album' (some entries omit 'rpm' but imply standard speed with LP).
  This broadens detection to handle Discogs data variability where 'RPM' is sometimes omitted.
  """
  if not descs:
    return False
  norm_tokens = {t.replace('.', '').replace(' ', '') for t in descs}
  has_combined = any('33' in t and 'rpm' in t for t in norm_tokens)
  if has_combined:
    return True
  has_33 = any('33' in t for t in norm_tokens)
  has_rpm = any('rpm' == t or t.endswith('rpm') for t in norm_tokens)
  has_lp_hint = any(t in {'lp', 'album'} for t in norm_tokens)
  return has_33 and (has_rpm or has_lp_hint)


def is_lp_33(basic: Dict, strict: bool = False, probable: bool = False) -> bool:
  """Determine if a release is a 33⅓ LP with minimal branching.

  Non-strict: any Vinyl format containing 'LP' or 'Album' qualifies (RPM optionally implied),
  OR a 12" record that clearly indicates 33 RPM.
  Strict: require Vinyl with LP/Album and evidence of 33 RPM per _desc_set_has_33rpm.
  Probable (probable=True): include Vinyl LP/Album unless a description explicitly indicates 45 or 78 RPM; still include 12" + 33 RPM.
  """
  vinyl_formats = [f for f in (basic.get("formats") or []) if (f.get("name") or "").strip().lower() == "vinyl"]
  if not vinyl_formats:
    return False
  size_tokens = {"12\"", "12”", "12in", "12-inch"}
  desc_sets = [
    {d.strip().lower() for d in (f.get("descriptions") or []) if d}
    for f in vinyl_formats
  ]
  if strict:
    return any((("lp" in s) or ("album" in s)) and _desc_set_has_33rpm(s) for s in desc_sets)

  if probable:
    # Reject if any LP/Album set has an explicit 45 or 78 indicator
    def has_45_or_78(s: set[str]) -> bool:
      norm = {t.replace('.', '').replace(' ', '') for t in s}
      return any('45' in t for t in norm) or any('78' in t for t in norm)
    return any((("lp" in s) or ("album" in s)) and not has_45_or_78(s) for s in desc_sets)

  return any(
    (("lp" in s) or ("album" in s)) or (_desc_set_has_33rpm(s) and (s & size_tokens))
    for s in desc_sets
  )


TRAILING_NUMERIC_RE = re.compile(r"\s*\((\d+)\)$")


def strip_discogs_numeric_suffix(name: str) -> str:
  # Remove trailing " (2)" etc.
  return TRAILING_NUMERIC_RE.sub("", name or "").strip()


def normalize_apostrophes(s: str) -> str:
  # Normalize typographic apostrophes to straight
  return (s or "").replace("’", "'")


def build_artist_display(basic: Dict) -> str:
  artists = basic.get("artists") or []
  if not artists:
    return basic.get("artist") or basic.get("title") or ""
  parts = []
  for a in artists:
    nm = a.get("name") or ""
    nm = strip_discogs_numeric_suffix(nm)
    parts.append(nm)
    j = a.get("join") or ""
    if j:
      parts.append(j)
      parts.append(" ")
  text = "".join(parts).strip()
  # Clean redundant spaces around joins
  return re.sub(r"\s+([&,+]|feat\.|with)\s+", r" \1 ", text, flags=re.IGNORECASE)


def _normalize_exclude_name(s: str) -> str:
  return re.sub(r"\s+", " ", (s or "").strip().lower())


def is_band_like(first: str, last: str) -> bool:
  band_adjectives = {
    "big", "small", "little",
    "bad", "good", "great",
    "new", "old", "young",
    "black", "white", "blue", "red", "green",
    "wild", "sweet",
  }
  band_terms = {
    "band", "trio", "quartet", "quintet", "sextet", "septet", "octet", "nonet",
    "orchestra", "ensemble", "choir", "chorale", "collective", "project", "group",
    "crew", "players", "brothers", "sisters", "family", "experience"
  }
  common_first_names = {
    "john","james","michael","robert","david","william","richard","thomas","charles","joseph",
    "christopher","daniel","paul","mark","donald","george","kenneth","steven","edward","brian",
    "ronald","anthony","kevin","jason","matthew","gary","timothy","jose","larry","jeffrey",
    "frank","scott","eric","stephen","andrew","raymond","gregory","joshua","jerry","dennis",
    "walter","patrick","peter","harold","douglas","henry","carl","arthur","ryan","roger",
    "joe","juan","jack","albert","jonathan","justin","terry","gerald","keith","samuel","willie",
    "ralph","lawrence","nicholas","roy","benjamin","bruce","brandon","adam","harry","fred","wayne",
    "billy","steve","louis","jeremy","aaron","randy","howard","eugene","carlos","russell","bobby",
    "victor","martin","ernest","phillip","todd","jesse","craig","alan","shawn","clarence","sean",
    "philip","chris","johnny","earl","jimmy","antonio","danny","bryan","tony","luis","miles","bruce",
    "neil","nick","lou","chuck","ian","alex","noel","bobby","billy"
  }
  first_low, last_low = first.lower(), last.lower()
  if last_low in band_terms:
    return True
  if last_low.endswith('s') and first_low not in common_first_names:
    return True
  if first_low in band_adjectives and last_low not in common_first_names:
    return True
  return False

def is_valid_two_word(tokens: list[str]) -> bool:
  if not all(re.match(r"[A-Za-z'\-]+$", t) for t in tokens):
    return False
  if any(t.lower() in {"the", "and", "&"} for t in tokens):
    return False
  return True

def flip_three_word(tokens: list[str]) -> Optional[str]:
  first, middle, last = tokens
  if first.lower() in {"the", "and", "&"}:
    return None
  middle_norm = middle.lower().strip('.')
  particles = {"de", "del", "van", "von", "da", "di", "la", "le", "du", "do", "dos", "das", "st"}
  if len(middle_norm) == 1 or middle.endswith('.') or middle_norm in particles:
    return f"{last}, {first} {middle}".lower()
  return None

def _last_name_first_key(artist_clean: str, allow_3: bool, exclude_set: Set[str], safe_bands: bool = False) -> Optional[str]:
  """Last-name-first heuristic with options:
  - Only flips two-word personal names by default.
  - Optionally flips certain three-word names when middle token is an initial or known particle.
  - Respects an exclude set (case-insensitive normalized names).
  """
  norm = _normalize_exclude_name(artist_clean)
  if norm in exclude_set:
    return None
  # Split on '/' or ',' to handle multi-artist strings, use first artist for sorting
  first_artist = re.split(r"/|,", artist_clean)[0].strip()
  tokens = [t for t in re.split(r"\s+", first_artist) if t]
  if len(tokens) == 2:
    if safe_bands and is_band_like(tokens[0], tokens[1]):
      return None
    if not is_valid_two_word(tokens):
      return None
    return f"{tokens[1]}, {tokens[0]}".lower()
  if allow_3 and len(tokens) == 3:
    return flip_three_word(tokens)
  # If not a personal name, fallback to original string (lowercased, stripped)
  return first_artist.lower()


def make_sort_keys(
  artist_display: str,
  title: str,
  extra_articles: List[str],
  last_name_first: bool = False,
  lnf_allow_3: bool = False,
  lnf_exclude: Optional[Set[str]] = None,
  lnf_safe_bands: bool = False,
) -> Tuple[str, str]:
  def strip_articles(text: str) -> str:
    if not text:
      return ""
    t = normalize_apostrophes(text).strip()
    # Default English articles
    articles = ["the", "a", "an"] + [a.strip().lower() for a in extra_articles if a.strip()]
    low = t.lower()
    for art in articles:
      art = art.rstrip("'")  # handle l' vs l’ in extra list gracefully
      # exact article followed by space or apostrophe
      if low.startswith(art + " "):
        return t[len(art) + 1 :].strip()
      if art and low.startswith(art + "'"):
        return t[len(art) + 1 :].strip()
    return t

  # For artists, also drop Discogs numeric suffixes
  artist_clean = strip_discogs_numeric_suffix(artist_display).strip()
  sort_artist_base = strip_articles(artist_clean).lower()
  if last_name_first:
    flipped = _last_name_first_key(artist_clean, allow_3=lnf_allow_3, exclude_set=(lnf_exclude or set()), safe_bands=lnf_safe_bands)
    if flipped:
      sort_artist_base = flipped
  return (sort_artist_base, strip_articles(title).lower())


def format_string(basic: Dict) -> str:
  """Build a concise format string from Discogs format entries.

  Each format entry may include qty, name, descriptions. We collapse them
  into semicolon-delimited segments. Cognitive complexity is kept low by
  extracting tiny helpers and avoiding deep nesting.
  """

  def build_piece(fmt: Dict) -> Optional[str]:
    name = (fmt.get("name") or "").strip()
    qty = (fmt.get("qty") or "").strip()
    desc_list = fmt.get("descriptions", []) or []
    descs = ", ".join(d.strip() for d in desc_list if d.strip())
    qty_prefix = f"{qty}x" if qty and qty != "1" else ""
    base = f"{qty_prefix}{name}" if name else qty_prefix.rstrip("x")
    if descs and base:
      return f"{base}, {descs}".strip()
    if descs:
      return descs
    return base or None

  formats = basic.get("formats", []) or []
  pieces = [p for fmt in formats if (p := build_piece(fmt))]
  return "; ".join(pieces)


def label_and_catno(basic: Dict) -> Tuple[str, str]:
  lbls = basic.get("labels", []) or []
  if not lbls:
    return "", ""
  # Prefer first label entry
  first = lbls[0]
  return (first.get("name") or "", first.get("catno") or "")


def is_vinyl_45(basic: Dict) -> bool:
  """Detect 7" 45 RPM vinyl singles.

  Requires a Vinyl format entry with size token ~7" and a description containing 45 and rpm.
  Avoids matching 12" 45 RPM maxis by requiring the ~7" size token.
  """
  vinyl_formats = [f for f in (basic.get("formats") or []) if (f.get("name") or "").strip().lower() == "vinyl"]
  if not vinyl_formats:
    return False
  size_tokens = {"7\"", "7”", "7in", "7-inch"}
  for f in vinyl_formats:
    descs = {d.strip().lower() for d in (f.get("descriptions") or []) if d}
    if descs & size_tokens and any("45" in d and "rpm" in d for d in descs):
      return True
  return False


def is_cd_format(basic: Dict) -> bool:
  """Detect CD or CDr formats."""
  for f in (basic.get("formats") or []):
    name = (f.get("name") or "").strip().lower()
    if name in {"cd", "cdr"}:
      return True
  return False


def build_release_row(
  basic: Dict,
  item: Dict,
  extra_articles: List[str],
  last_name_first: bool,
  lnf_allow_3: bool,
  lnf_exclude: Optional[Set[str]],
  lnf_safe_bands: bool,
) -> ReleaseRow:
  title = basic.get("title") or ""
  artist_disp = build_artist_display(basic)
  year_raw = basic.get("year")
  year = int(year_raw) if (year_raw and str(year_raw).isdigit()) else None
  label, catno = label_and_catno(basic)
  fmt_desc = format_string(basic)
  rel_id = basic.get("id")
  url = f"https://www.discogs.com/release/{rel_id}" if rel_id else ""
  sort_artist, sort_title = make_sort_keys(
    artist_disp,
    title,
    extra_articles,
    last_name_first=last_name_first,
    lnf_allow_3=lnf_allow_3,
    lnf_exclude=lnf_exclude,
    lnf_safe_bands=lnf_safe_bands,
  )
  # Get thumbnail URLs - Discogs provides 'thumb' (small) and 'cover_image' (larger)
  thumb_url = basic.get("thumb") or ""
  cover_image_url = basic.get("cover_image") or ""
  
  return ReleaseRow(
    artist_display=artist_disp,
    title=title,
    year=year,
    label=label,
    catno=catno,
    country=basic.get("country") or "",
    format_str=fmt_desc,
    discogs_url=url,
    notes=(item.get("notes") or ""),
    release_id=int(rel_id) if isinstance(rel_id, int) or (isinstance(rel_id, str) and rel_id.isdigit()) else None,
    sort_artist=sort_artist,
    sort_title=sort_title,
    thumb_url=thumb_url,
    cover_image_url=cover_image_url,
  )

def collect_lp_rows(
    headers: Dict[str, str],
    username: str,
    per_page: int,
    max_pages: Optional[int],
    extra_articles: List[str],
    lp_strict: bool = False,
    lp_probable: bool = False,
    debug_stats: Optional[Dict[str, int]] = None,
    last_name_first: bool = False,
    lnf_allow_3: bool = False,
    lnf_exclude: Optional[Set[str]] = None,
    lnf_safe_bands: bool = False,
    collect_exclusions: bool = False,
) -> List[ReleaseRow]:
    """
    Collects LP rows from a Discogs collection, filtering and tracking stats/exclusions.
    Refactored to reduce cognitive complexity by splitting logic into helpers.
    """
    rows: List[ReleaseRow] = []
    stats = {"scanned": 0, "vinyl": 0, "vinyl_lp": 0, "vinyl_lp_33": 0}
    excluded_probable: List[Dict] = []

    def basic_info(item: Dict) -> Dict:
        return item.get("basic_information") or {}

    def update_stats(basic: Dict) -> None:
        stats["scanned"] += 1
        fmts = basic.get("formats", []) or []
        is_vinyl = any((f.get("name") or "").strip().lower() == "vinyl" for f in fmts)
        if is_vinyl:
            stats["vinyl"] += 1
            lp_flag = any(
                any((d.strip().lower() in {"lp", "album"}) for d in (f.get("descriptions") or []))
                for f in fmts if (f.get("name") or "").strip().lower() == "vinyl"
            )
            if lp_flag:
                stats["vinyl_lp"] += 1
                lp_33_flag = any(
                    any(("33" in d.strip().lower() and "rpm" in d.strip().lower()) for d in (f.get("descriptions") or []))
                    for f in fmts if (f.get("name") or "").strip().lower() == "vinyl"
                )
                if lp_33_flag:
                    stats["vinyl_lp_33"] += 1

    def build_row(basic: Dict, item: Dict) -> ReleaseRow:
        title = basic.get("title") or ""
        artist_disp = build_artist_display(basic)
        year_raw = basic.get("year")
        year = int(year_raw) if (year_raw and str(year_raw).isdigit()) else None
        label, catno = label_and_catno(basic)
        fmt_desc = format_string(basic)
        rel_id = basic.get("id")
        master_id_raw = basic.get("master_id")
        url = f"https://www.discogs.com/release/{rel_id}" if rel_id else ""
        thumb_url = basic.get("thumb") or ""
        cover_image_url = basic.get("cover_image") or ""
        sort_artist, sort_title = make_sort_keys(
            artist_disp,
            title,
            extra_articles,
            last_name_first=last_name_first,
            lnf_allow_3=lnf_allow_3,
            lnf_exclude=lnf_exclude,
            lnf_safe_bands=lnf_safe_bands,
        )
        return ReleaseRow(
            artist_display=artist_disp,
            title=title,
            year=year,
            label=label,
            catno=catno,
            country=basic.get("country") or "",
            format_str=fmt_desc,
            discogs_url=url,
            notes=(item.get("notes") or ""),
            release_id=int(rel_id) if isinstance(rel_id, int) or (isinstance(rel_id, str) and rel_id.isdigit()) else None,
            master_id=int(master_id_raw) if isinstance(master_id_raw, int) or (isinstance(master_id_raw, str) and master_id_raw.isdigit()) else None,
            sort_artist=sort_artist,
            sort_title=sort_title,
            thumb_url=thumb_url,
            cover_image_url=cover_image_url,
        )

    def should_exclude(basic: Dict) -> bool:
        return not is_lp_33(basic, strict=lp_strict, probable=lp_probable)

    def track_exclusion(basic: Dict) -> None:
        if collect_exclusions and lp_probable and not lp_strict:
            excluded_probable.append(basic)

    def process_item(item: Dict) -> None:
        basic = basic_info(item)
        if not basic:
            return
        update_stats(basic)
        if should_exclude(basic):
            track_exclusion(basic)
            return
        rows.append(build_row(basic, item))

    for item in iterate_collection(headers, username, per_page=per_page, max_pages=max_pages):
        process_item(item)

    if debug_stats is not None:
        debug_stats.clear()
        debug_stats.update(stats)
    # Attach excluded basics list to a special attribute for later retrieval (if needed)
    if collect_exclusions and lp_probable and not lp_strict:
        setattr(rows, "excluded_probable_basics", excluded_probable)
    return rows


def collect_45_rows(
  headers: Dict[str, str],
  username: str,
  per_page: int,
  max_pages: Optional[int],
  extra_articles: List[str],
  last_name_first: bool = False,
  lnf_allow_3: bool = False,
  lnf_exclude: Optional[Set[str]] = None,
  lnf_safe_bands: bool = False,
) -> List[ReleaseRow]:
  rows: List[ReleaseRow] = []
  for item in iterate_collection(headers, username, per_page=per_page, max_pages=max_pages):
    basic = item.get("basic_information") or {}
    if not basic:
      continue
    if is_vinyl_45(basic):
      rows.append(
        build_release_row(
          basic,
          item,
          extra_articles,
          last_name_first=last_name_first,
          lnf_allow_3=lnf_allow_3,
          lnf_exclude=lnf_exclude,
          lnf_safe_bands=lnf_safe_bands,
        )
      )
  return rows


def collect_cd_rows(
  headers: Dict[str, str],
  username: str,
  per_page: int,
  max_pages: Optional[int],
  extra_articles: List[str],
  last_name_first: bool = False,
  lnf_allow_3: bool = False,
  lnf_exclude: Optional[Set[str]] = None,
  lnf_safe_bands: bool = False,
) -> List[ReleaseRow]:
  rows: List[ReleaseRow] = []
  for item in iterate_collection(headers, username, per_page=per_page, max_pages=max_pages):
    basic = item.get("basic_information") or {}
    if not basic:
      continue
    if is_cd_format(basic):
      rows.append(
        build_release_row(
          basic,
          item,
          extra_articles,
          last_name_first=last_name_first,
          lnf_allow_3=lnf_allow_3,
          lnf_exclude=lnf_exclude,
          lnf_safe_bands=lnf_safe_bands,
        )
      )
  return rows


def is_various_artist(artist_disp: str) -> bool:
    a = (artist_disp or "").strip().lower()
    return a in {"various", "various artists"}

def sort_key_price_desc(r: ReleaseRow):
    return (r.lowest_price is None, -(r.lowest_price or 0))

def sort_key_price_asc(r: ReleaseRow):
    return (r.lowest_price is None, r.lowest_price or 0)

def sort_key_year(r: ReleaseRow):
    return (r.year or 9999, r.sort_artist, r.sort_title)

def sort_key_general(r: ReleaseRow, various_policy: str, sort_by: str) -> tuple:
    is_var = is_various_artist(r.artist_display)
    var_flag = 1 if (various_policy == "last" and is_var) else 0
    year_val = r.year if isinstance(r.year, int) else 9999

    if various_policy == "title" and is_var:
        primary = r.sort_title
        secondary = r.sort_title
        tie = r.sort_artist
    elif sort_by == "title":
        primary = r.sort_title
        secondary = r.sort_artist
        tie = r.sort_title
    else:
        primary = r.sort_artist
        secondary = r.sort_title
        tie = r.sort_artist

    return (var_flag, primary, secondary, year_val, tie)

def sort_rows(rows: List[ReleaseRow], various_policy: str, sort_by: str = "artist") -> List[ReleaseRow]:
    """Sort rows by the specified field.

    Args:
        rows: List of ReleaseRow objects
        various_policy: How to handle Various Artists ("normal", "last", "title")
        sort_by: Field to sort by ("artist", "title", "price_asc", "price_desc", "year")
    """
    if sort_by == "price_desc":
        return sorted(rows, key=sort_key_price_desc)

    if sort_by == "price_asc":
        return sorted(rows, key=sort_key_price_asc)

    if sort_by == "year":
        return sorted(rows, key=sort_key_year)

    return sorted(rows, key=lambda r: sort_key_general(r, various_policy, sort_by))


def get_divider_line(r: ReleaseRow, current: Optional[str], dividers: bool) -> Tuple[Optional[str], Optional[str]]:
    if not dividers:
        return current, None
    sa = r.sort_artist.strip()
    first = sa[0].upper() if sa else "#"
    if not first.isalpha():
        first = "#"
    if current != first:
        return first, f"=== {first} ==="
    return current, None

def get_year_str(r: ReleaseRow) -> str:
    return f" ({r.year})" if r.year else ""

def get_label_part(r: ReleaseRow) -> str:
    return f" [{r.label} {r.catno}]".rstrip() if (r.label or r.catno) else ""

def get_country_part(r: ReleaseRow, show_country: bool) -> str:
    return f" {{{r.country}}}" if (show_country and r.country) else ""

def get_price_part(r: ReleaseRow, show_price: bool) -> str:
    if not show_price:
        return ""
    if r.lowest_price is not None and r.num_for_sale and r.num_for_sale > 0:
        return f" - {r.lowest_price:.0f} {r.price_currency}+ ({r.num_for_sale} for sale)"
    return " [Not listed]"

def format_txt_line(
    r: ReleaseRow,
    artist_width: int,
    title_width: int,
    align: bool,
    show_country: bool,
    show_price: bool
) -> str:
    year_str = get_year_str(r)
    label_part = get_label_part(r)
    country_part = get_country_part(r, show_country)
    price_part = get_price_part(r, show_price)
    if align:
        return f"{r.artist_display.ljust(artist_width)} | {r.title.ljust(title_width)}{year_str}{label_part}{country_part}{price_part}".rstrip()
    return f"{r.artist_display} — {r.title}{year_str}{label_part}{country_part}{price_part}".rstrip()

def generate_txt_lines(
    rows: List[ReleaseRow],
    dividers: bool = False,
    align: bool = False,
    show_country: bool = False,
    show_price: bool = False
) -> List[str]:
    """Return the lines that would appear in the TXT output.

    Used by both CLI writer and GUI preview to avoid duplication.
    """
    artist_width = max((len(r.artist_display) for r in rows), default=0) if align else 0
    title_width = max((len(r.title) for r in rows), default=0) if align else 0

    lines: List[str] = []
    current_div: Optional[str] = None
    for r in rows:
        current_div, div_line = get_divider_line(r, current_div, dividers)
        if div_line:
            lines.append(div_line)
        lines.append(format_txt_line(r, artist_width, title_width, align, show_country, show_price))
    return lines


def write_txt(rows: List[ReleaseRow], out_path: Path, dividers: bool = False,
              align: bool = False, show_country: bool = False) -> None:
  lines = generate_txt_lines(rows, dividers=dividers, align=align, show_country=show_country)
  with out_path.open("w", encoding="utf-8") as f:
    for line in lines:
      f.write(line + "\n")


def write_json(rows: List[ReleaseRow], out_path: Path) -> None:
  import json
  data = [
    {
      "artist": r.artist_display,
      "title": r.title,
      "year": r.year,
      "label": r.label,
      "catno": r.catno,
      "country": r.country,
      "format": r.format_str,
      "discogs_url": r.discogs_url,
      "notes": r.notes,
      "sort_artist": r.sort_artist,
      "sort_title": r.sort_title,
    }
    for r in rows
  ]
  with out_path.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


def rows_to_json(rows: List[ReleaseRow]) -> List[Dict[str, object]]:
  return [
    {
      "artist": r.artist_display,
      "title": r.title,
      "year": r.year,
      "label": r.label,
      "catno": r.catno,
      "country": r.country,
      "format": r.format_str,
      "discogs_url": r.discogs_url,
      "notes": r.notes,
      "sort_artist": r.sort_artist,
      "sort_title": r.sort_title,
    }
    for r in rows
  ]


def write_csv(rows: List[ReleaseRow], out_path: Path) -> None:
  cols = [
    "Artist",
    "Title",
    "Year",
    "Label",
    "CatNo",
    "Country",
    "Format",
    "DiscogsURL",
    "Notes",
  ]
  with out_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(cols)
    for r in rows:
      writer.writerow(
        [
          r.artist_display,
          r.title,
          r.year or "",
          r.label,
          r.catno,
          r.country,
          r.format_str,
          r.discogs_url,
          r.notes,
        ]
      )


def main() -> None:
    args = parse_args()
    token = get_token(args.token)
    headers = discogs_headers(token, args.user_agent)

    print(f"Discogs LP Sorter v{VERSION}")

    ident = get_identity(headers)
    username = ident.get("username")
    if not username:
        sys.exit("Error: Could not determine username from token.")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extra_articles = [a.strip() for a in (args.articles_extra or "").split(",") if a.strip()]

    rows, _ = fetch_and_report_lp_rows(args, headers, username, extra_articles)
    if not rows:
        return

    rows_sorted = sort_rows(rows, args.various_policy)
    write_main_outputs(args, out_dir, rows_sorted)

    rows45_sorted = handle_optional_45s(args, headers, username, extra_articles, out_dir)
    rows_cd_sorted = handle_optional_cds(args, headers, username, extra_articles, out_dir)

    print_category_summary(rows_sorted, rows45_sorted, rows_cd_sorted)

    handle_combined_json(args, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted)
    handle_probable_exclusions(args, out_dir, rows)
    handle_valuable_export(args, out_dir, headers, rows_sorted, rows45_sorted, rows_cd_sorted)

def fetch_and_report_lp_rows(args, headers, username, extra_articles):
    dbg: Optional[Dict[str, int]] = {} if args.debug_stats else None
    print(f"Fetching collection for user '{username}'...")
    rows = collect_lp_rows(
        headers=headers,
        username=username,
        per_page=max(1, min(int(args.per_page), 100)),
        max_pages=args.max_pages,
        extra_articles=extra_articles,
        lp_strict=bool(args.lp_strict),
        lp_probable=bool(getattr(args, "lp_probable_33", False)),
        debug_stats=dbg,
        last_name_first=bool(args.last_name_first),
        lnf_allow_3=bool(getattr(args, "lnf_allow_3", False)),
        lnf_exclude={_normalize_exclude_name(s) for s in (getattr(args, "lnf_exclude", "").split(";") if getattr(args, "lnf_exclude", "") else []) if s.strip()},
        lnf_safe_bands=bool(getattr(args, "lnf_safe_bands", False)),
        collect_exclusions=bool(getattr(args, "report_filters", False)),
    )
    if not rows:
        print("No matching 33⅓ RPM LPs found.")
        if args.debug_stats:
            print("Tip: Re-run without strict RPM requirement (default) or enable debug stats with --debug-stats.")
        return [], dbg
    if args.debug_stats and dbg is not None:
        print(
            f"Stats: scanned={dbg.get('scanned', 0)}, vinyl={dbg.get('vinyl', 0)}, "
            f"vinyl+LP={dbg.get('vinyl_lp', 0)}, vinyl+LP+33rpm={dbg.get('vinyl_lp_33', 0)}"
        )
        if getattr(args, "report_filters", False) and getattr(args, "lp_probable_33", False) and not getattr(args, "lp_strict", False):
            excl = getattr(rows, "excluded_probable_basics", [])
            print(f"Probable exclusions (explicit 45/78): {len(excl)}")
    return rows, dbg

def write_main_outputs(args, out_dir, rows_sorted):
    txt_path = out_dir / "vinyl_shelf_order.txt"
    csv_path = out_dir / "vinyl_shelf_order.csv"
    write_txt(rows_sorted, txt_path, dividers=bool(args.dividers), align=bool(args.txt_align), show_country=bool(args.show_country))
    write_csv(rows_sorted, csv_path)
    if args.json:
        json_path = out_dir / "vinyl_shelf_order.json"
        write_json(rows_sorted, json_path)
    print(f"Wrote: {txt_path}")
    print(f"Wrote: {csv_path}")
    if args.json:
        print(f"Wrote: {json_path}")

def handle_optional_45s(args, headers, username, extra_articles, out_dir):
    rows45_sorted: List[ReleaseRow] = []
    if getattr(args, "include_45s", False):
        rows45 = collect_45_rows(
            headers=headers,
            username=username,
            per_page=max(1, min(int(args.per_page), 100)),
            max_pages=args.max_pages,
            extra_articles=extra_articles,
            last_name_first=bool(args.last_name_first),
            lnf_allow_3=bool(getattr(args, "lnf_allow_3", False)),
            lnf_exclude={_normalize_exclude_name(s) for s in (getattr(args, "lnf_exclude", "").split(";") if getattr(args, "lnf_exclude", "") else []) if s.strip()},
            lnf_safe_bands=bool(getattr(args, "lnf_safe_bands", False)),
        )
        rows45_sorted = sort_rows(rows45, args.various_policy)
        txt45 = out_dir / "vinyl45_shelf_order.txt"
        csv45 = out_dir / "vinyl45_shelf_order.csv"
        write_txt(rows45_sorted, txt45, dividers=bool(args.dividers), align=bool(args.txt_align), show_country=bool(args.show_country))
        write_csv(rows45_sorted, csv45)
        if args.json:
            json45 = out_dir / "vinyl45_shelf_order.json"
            write_json(rows45_sorted, json45)
        print(f"Wrote: {txt45}")
        print(f"Wrote: {csv45}")
        if args.json:
            print(f"Wrote: {json45}")
    return rows45_sorted

def handle_optional_cds(args, headers, username, extra_articles, out_dir):
    rows_cd_sorted: List[ReleaseRow] = []
    if getattr(args, "include_cds", False):
        rows_cd = collect_cd_rows(
            headers=headers,
            username=username,
            per_page=max(1, min(int(args.per_page), 100)),
            max_pages=args.max_pages,
            extra_articles=extra_articles,
            last_name_first=bool(args.last_name_first),
            lnf_allow_3=bool(getattr(args, "lnf_allow_3", False)),
            lnf_exclude={_normalize_exclude_name(s) for s in (getattr(args, "lnf_exclude", "").split(";") if getattr(args, "lnf_exclude", "") else []) if s.strip()},
            lnf_safe_bands=bool(getattr(args, "lnf_safe_bands", False)),
        )
        rows_cd_sorted = sort_rows(rows_cd, args.various_policy)
        txtcd = out_dir / "cd_shelf_order.txt"
        csvcd = out_dir / "cd_shelf_order.csv"
        write_txt(rows_cd_sorted, txtcd, dividers=bool(args.dividers), align=bool(args.txt_align), show_country=bool(args.show_country))
        write_csv(rows_cd_sorted, csvcd)
        if args.json:
            jsoncd = out_dir / "cd_shelf_order.json"
            write_json(rows_cd_sorted, jsoncd)
        print(f"Wrote: {txtcd}")
        print(f"Wrote: {csvcd}")
        if args.json:
            print(f"Wrote: {jsoncd}")
    return rows_cd_sorted

def print_category_summary(rows_sorted, rows45_sorted, rows_cd_sorted):
    summary_parts = [f"LP: {len(rows_sorted)}"]
    if rows45_sorted:
        summary_parts.append(f"45s: {len(rows45_sorted)}")
    if rows_cd_sorted:
        summary_parts.append(f"CDs: {len(rows_cd_sorted)}")
    print("Summary: " + " • ".join(summary_parts))

def handle_combined_json(args, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted):
    if args.json and (rows45_sorted or rows_cd_sorted):
        import json as _json
        combined = []
        for r in rows_sorted:
            combined.append({"media_type": "LP", **rows_to_json([r])[0]})
        for r in rows45_sorted:
            combined.append({"media_type": "45", **rows_to_json([r])[0]})
        for r in rows_cd_sorted:
            combined.append({"media_type": "CD", **rows_to_json([r])[0]})
        combo_path = out_dir / "all_media_shelf_order.json"
        with combo_path.open("w", encoding="utf-8") as f:
            _json.dump(combined, f, ensure_ascii=False, indent=2)
        print(f"Wrote: {combo_path}")

def _write_probable_exclusion_report(excl_basics, out_dir):
    report_path = out_dir / "excluded_probable_lp.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("=== LPs excluded in probable 33 mode (explicit 45/78 descriptors) ===\n")
        for b in excl_basics:
            title = b.get("title") or ""
            artists = build_artist_display(b)
            desc_tokens = []
            for fmt in (b.get("formats") or []):
                if (fmt.get("name") or "").strip().lower() == "vinyl":
                    desc_tokens.extend([d for d in (fmt.get("descriptions") or []) if d])
            line = f"{artists} — {title} | descriptors: {', '.join(desc_tokens)}"
            f.write(line + "\n")
    print(f"Wrote: {report_path}")

def handle_probable_exclusions(args, out_dir, rows):
    should_report = (
        getattr(args, "report_filters", False)
        and getattr(args, "lp_probable_33", False)
        and not getattr(args, "lp_strict", False)
    )
    if not should_report:
        return
    excl_basics = getattr(rows, "excluded_probable_basics", [])
    if excl_basics:
        _write_probable_exclusion_report(excl_basics, out_dir)

def handle_valuable_export(args, out_dir, headers, rows_sorted, rows45_sorted, rows_cd_sorted):
    if not getattr(args, "valuable_sek", None):
        return
    threshold = float(args.valuable_sek)
    candidates = _gather_valuable_candidates(rows_sorted, rows45_sorted, rows_cd_sorted)
    print(f"Evaluating prices for {len(candidates)} items (threshold: {threshold:.0f} SEK)…")
    valuable = _find_valuable_items(candidates, headers, threshold)
    _write_valuable_report(valuable, threshold, args, out_dir)

def _gather_valuable_candidates(rows_sorted, rows45_sorted, rows_cd_sorted):
    candidates: List[ReleaseRow] = []
    candidates.extend(rows_sorted)
    if rows45_sorted:
        candidates.extend(rows45_sorted)
    if rows_cd_sorted:
        candidates.extend(rows_cd_sorted)
    return candidates

def _lowest_price_sek(rel_id: int, headers) -> Optional[float]:
    url = f"{API_BASE}/releases/{rel_id}"
    resp = api_get(url, headers, params={"curr_abbr": "SEK"})
    try:
        lp = resp.json().get("lowest_price")
        return float(lp) if lp is not None else None
    except Exception:
        return None

def _find_valuable_items(candidates, headers, threshold):
    price_cache: Dict[int, Optional[float]] = {}
    valuable: List[tuple[ReleaseRow, float]] = []
    for r in candidates:
        rid = r.release_id
        if not isinstance(rid, int):
            continue
        if rid not in price_cache:
            price_cache[rid] = _lowest_price_sek(rid, headers)
        p = price_cache[rid]
        if p is not None and p >= threshold:
            valuable.append((r, p))
    return valuable

def _write_valuable_report(valuable, threshold, args, out_dir):
    if valuable:
        out_path = out_dir / f"valuable_over_{int(threshold)}kr.txt"
        with out_path.open("w", encoding="utf-8") as f:
            f.write(f"=== Valuable items >= {int(threshold)} SEK ===\n")
            for r, p in valuable:
                line = generate_txt_lines([r], dividers=False, align=False, show_country=bool(args.show_country))[0]
                f.write(f"{line} [~{p:.0f} SEK]\n")
        print(f"Wrote: {out_path} ({len(valuable)} items)")
    else:
        print(f"No items found at or above {int(threshold)} SEK.")


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\nInterrupted.")
    sys.exit(130)
  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
