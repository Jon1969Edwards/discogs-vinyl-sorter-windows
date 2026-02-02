"""
Sorting and normalization functions for Discogs collection.

This module provides functions for:
- Filtering releases by format (LP 33⅓, 45 RPM, CD)
- Normalizing artist and title strings for sorting
- Building release data rows
- Sorting releases by various criteria
"""

from __future__ import annotations

import re
import sys
from typing import Dict, Iterable, List, Optional, Set, Tuple

from core.models import ReleaseRow
from core.api import iterate_collection, fetch_release_price, api_get, API_BASE


# ============================================================================
# Format detection helpers
# ============================================================================

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
  size_tokens = {"12\"", '12"', "12in", "12-inch"}
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


def is_vinyl_45(basic: Dict) -> bool:
  """Detect 7" 45 RPM vinyl singles.

  Requires a Vinyl format entry with size token ~7" and a description containing 45 and rpm.
  Avoids matching 12" 45 RPM maxis by requiring the ~7" size token.
  """
  vinyl_formats = [f for f in (basic.get("formats") or []) if (f.get("name") or "").strip().lower() == "vinyl"]
  if not vinyl_formats:
    return False
  size_tokens = {"7\"", "7in", "7-inch"}
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


# ============================================================================
# String normalization and artist/title processing
# ============================================================================

TRAILING_NUMERIC_RE = re.compile(r"\s*\((\d+)\)$")


def strip_discogs_numeric_suffix(name: str) -> str:
  # Remove trailing " (2)" etc.
  return TRAILING_NUMERIC_RE.sub("", name or "").strip()


def normalize_apostrophes(s: str) -> str:
  # Normalize typographic apostrophes to straight
  return (s or "").replace("'", "'")


def _normalize_exclude_name(s: str) -> str:
  return re.sub(r"\s+", " ", (s or "").strip().lower())


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


# ============================================================================
# Last-name-first heuristics
# ============================================================================

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
  first_artist = re.split(r"[/,]", artist_clean)[0].strip()
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
      art = art.rstrip("'")  # handle l' vs l' in extra list gracefully
      # exact article followed by space or apostrophe
      if low.startswith(art + " "):
        return t[len(art) + 1 :].strip()
      if art and low.startswith(art + "'"):
        return t[len(art) + 1 :].strip()
    return t

  # For sorting, use only the first artist (before '/' or ',')
  artist_first = artist_display.split('/')[0].split(',')[0].strip()
  artist_clean = strip_discogs_numeric_suffix(artist_first).strip()
  sort_artist_base = strip_articles(artist_clean).lower()
  if last_name_first:
    flipped = _last_name_first_key(artist_clean, allow_3=lnf_allow_3, exclude_set=(lnf_exclude or set()), safe_bands=lnf_safe_bands)
    if flipped:
      sort_artist_base = flipped
  return (sort_artist_base, strip_articles(title).lower())


# ============================================================================
# Format and label helpers
# ============================================================================

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


# ============================================================================
# Build release row
# ============================================================================

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


# ============================================================================
# Collection row collectors
# ============================================================================

def _lp_basic_info(item: Dict) -> Dict:
    return item.get("basic_information") or {}

def _lp_update_stats(basic: Dict, stats: Dict[str, int]) -> None:
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

def _lp_build_row(
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

def _lp_should_exclude(basic: Dict, lp_strict: bool, lp_probable: bool) -> bool:
    return not is_lp_33(basic, strict=lp_strict, probable=lp_probable)

def _lp_track_exclusion(
    basic: Dict,
    collect_exclusions: bool,
    lp_probable: bool,
    lp_strict: bool,
    excluded_probable: List[Dict],
) -> None:
    if collect_exclusions and lp_probable and not lp_strict:
        excluded_probable.append(basic)

def _lp_process_item(
    item: Dict,
    stats: Dict[str, int],
    rows: List[ReleaseRow],
    excluded_probable: List[Dict],
    extra_articles: List[str],
    lp_strict: bool,
    lp_probable: bool,
    last_name_first: bool,
    lnf_allow_3: bool,
    lnf_exclude: Optional[Set[str]],
    lnf_safe_bands: bool,
    collect_exclusions: bool,
) -> None:
    basic = _lp_basic_info(item)
    if not basic:
        return
    _lp_update_stats(basic, stats)
    if _lp_should_exclude(basic, lp_strict, lp_probable):
        _lp_track_exclusion(basic, collect_exclusions, lp_probable, lp_strict, excluded_probable)
        return
    rows.append(
        _lp_build_row(
            basic,
            item,
            extra_articles,
            last_name_first,
            lnf_allow_3,
            lnf_exclude,
            lnf_safe_bands,
        )
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

    for item in iterate_collection(headers, username, per_page=per_page, max_pages=max_pages):
        _lp_process_item(
            item,
            stats,
            rows,
            excluded_probable,
            extra_articles,
            lp_strict,
            lp_probable,
            last_name_first,
            lnf_allow_3,
            lnf_exclude,
            lnf_safe_bands,
            collect_exclusions,
        )

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


# ============================================================================
# Sorting functions
# ============================================================================

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
