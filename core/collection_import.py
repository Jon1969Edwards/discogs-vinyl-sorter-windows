"""Load a vinyl collection from CSV or JSON into ReleaseRow records.

Accepts Spindle's own CSV/JSON exports and the common spreadsheet columns
(Artist, Title, Year, Label, CatNo, Country, Format, Notes). Optional
DiscogsURL / ReleaseID / CoverURL / ThumbURL columns round-trip extra fields.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from core.models import SOURCE_LOCAL, ReleaseRow
from core.sorting import detect_format_categories, make_sort_keys

_DISCOGS_RELEASE_RE = re.compile(
    r"(?:discogs\.com/(?:[^/]+/)?release/|api\.discogs\.com/releases/)(\d+)",
    re.IGNORECASE,
)

_KNOWN_FORMAT_NAMES = {
    "vinyl",
    "cd",
    "cdr",
    "cassette",
    "box set",
    "file",
    "flexi-disc",
    "flexi disc",
    "lathe cut",
    "shellac",
    "acetate",
    "dvd",
    "sacd",
    "minidisc",
    "8-track",
    "reel-to-reel",
    "dat",
}

_HEADER_ALIASES = {
    "artist": "artist",
    "artist_display": "artist",
    "title": "title",
    "year": "year",
    "label": "label",
    "catno": "catno",
    "cat_no": "catno",
    "catalog": "catno",
    "catalogue": "catno",
    "catalogno": "catno",
    "catalog_no": "catno",
    "country": "country",
    "format": "format",
    "format_str": "format",
    "discogsurl": "url",
    "discogs_url": "url",
    "url": "url",
    "sourceurl": "url",
    "source_url": "url",
    "notes": "notes",
    "coverurl": "cover",
    "cover_url": "cover",
    "cover": "cover",
    "cover_image_url": "cover",
    "coverimageurl": "cover",
    "thumburl": "thumb",
    "thumb_url": "thumb",
    "thumb": "thumb",
    "releaseid": "release_id",
    "release_id": "release_id",
    "id": "release_id",
    "source": "source",
    "item_id": "item_id",
    "itemid": "item_id",
    "sort_artist": "sort_artist",
    "sort_title": "sort_title",
    "format_categories": "format_categories",
}


class CollectionImportError(ValueError):
    """Raised when a collection file cannot be parsed."""


def parse_discogs_release_id(url_or_id: Any) -> Optional[int]:
    if url_or_id is None:
        return None
    if isinstance(url_or_id, int):
        return url_or_id if url_or_id > 0 else None
    text = str(url_or_id).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = _DISCOGS_RELEASE_RE.search(text)
    return int(match.group(1)) if match else None


def make_local_item_id(artist: str, title: str, year: Optional[int], catno: str) -> str:
    raw = f"{(artist or '').strip().lower()}|{(title or '').strip().lower()}|{year or ''}|{(catno or '').strip().lower()}"
    return "local:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def formats_from_format_str(format_str: str) -> List[Dict[str, Any]]:
    """Best-effort Discogs-like formats[] from a free-text Format column."""
    text = (format_str or "").strip()
    if not text:
        return []
    pieces = [p.strip() for p in re.split(r"[;|]", text) if p.strip()]
    parsed = [_piece_to_format(p) for p in pieces] if pieces else []
    return [f for f in parsed if f.get("name") or f.get("descriptions")]


def detect_format_categories_from_str(format_str: str) -> frozenset:
    basic = {"formats": formats_from_format_str(format_str)}
    return detect_format_categories(basic)


def load_collection_file(path: Path) -> List[ReleaseRow]:
    """Load CSV or JSON from ``path``. Raises CollectionImportError on failure."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        records = _read_csv_records(path)
    elif suffix == ".json":
        records = _read_json_records(path)
    else:
        raise CollectionImportError(
            f"Unsupported file type '{path.suffix}'. Import a .csv or .json collection."
        )
    rows = rows_from_records(records, source=SOURCE_LOCAL)
    if not rows:
        raise CollectionImportError(
            "No albums found. Each row needs at least an Artist or Title."
        )
    return rows


def rows_from_records(
    records: Iterable[Mapping[str, Any]],
    *,
    source: str = SOURCE_LOCAL,
) -> List[ReleaseRow]:
    rows: List[ReleaseRow] = []
    for raw in records:
        mapped = _normalize_record(raw)
        row = _record_to_row(mapped, default_source=source)
        if row is not None:
            rows.append(row)
    return rows


def row_to_record(row: ReleaseRow) -> Dict[str, Any]:
    return {
        "artist": row.artist_display,
        "title": row.title,
        "year": row.year,
        "label": row.label,
        "catno": row.catno,
        "country": row.country,
        "format": row.format_str,
        "discogs_url": row.discogs_url,
        "notes": row.notes,
        "release_id": row.release_id,
        "source": row.source,
        "item_id": row.item_id,
        "thumb_url": row.thumb_url,
        "cover_image_url": row.cover_image_url,
        "format_categories": sorted(row.format_categories),
        "sort_artist": row.sort_artist,
        "sort_title": row.sort_title,
    }


def _normalize_header(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return _HEADER_ALIASES.get(key, key)


def _normalize_record(raw: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in raw.items():
        mapped = _normalize_header(str(key))
        if mapped in _HEADER_ALIASES.values() or mapped in {
            "artist",
            "title",
            "year",
            "label",
            "catno",
            "country",
            "format",
            "url",
            "notes",
            "cover",
            "thumb",
            "release_id",
            "source",
            "item_id",
            "sort_artist",
            "sort_title",
            "format_categories",
        }:
            if mapped not in out or out[mapped] in (None, ""):
                out[mapped] = value
    return out


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_year(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    match = re.search(r"(18|19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def _parse_categories(value: Any) -> frozenset:
    if isinstance(value, (set, frozenset, list, tuple)):
        return frozenset(str(x) for x in value if x)
    if isinstance(value, str) and value.strip():
        parts = re.split(r"[\s,;|]+", value.strip())
        return frozenset(p for p in parts if p)
    return frozenset()


def _record_to_row(mapped: Mapping[str, Any], *, default_source: str) -> Optional[ReleaseRow]:
    artist = _as_str(mapped.get("artist"))
    title = _as_str(mapped.get("title"))
    if not artist and not title:
        return None
    format_str = _as_str(mapped.get("format"))
    url = _as_str(mapped.get("url") or mapped.get("discogs_url"))
    release_id = parse_discogs_release_id(mapped.get("release_id")) or parse_discogs_release_id(url)
    year = _parse_year(mapped.get("year"))
    catno = _as_str(mapped.get("catno"))
    categories = _parse_categories(mapped.get("format_categories"))
    if not categories:
        categories = detect_format_categories_from_str(format_str)
    item_id = _as_str(mapped.get("item_id"))
    if not item_id:
        item_id = f"discogs:{release_id}" if release_id else make_local_item_id(artist, title, year, catno)
    if url and release_id and "discogs.com" not in url.lower() and not url.startswith("http"):
        url = f"https://www.discogs.com/release/{release_id}"
    elif not url and release_id:
        url = f"https://www.discogs.com/release/{release_id}"
    sort_artist = _as_str(mapped.get("sort_artist"))
    sort_title = _as_str(mapped.get("sort_title"))
    if not sort_artist or not sort_title:
        sort_artist, sort_title = make_sort_keys(
            artist,
            title,
            extra_articles=[],
            last_name_first=True,
            lnf_allow_3=False,
            lnf_exclude=set(),
            lnf_safe_bands=True,
        )
    return ReleaseRow(
        artist_display=artist,
        title=title,
        year=year,
        label=_as_str(mapped.get("label")),
        catno=catno,
        country=_as_str(mapped.get("country")),
        format_str=format_str,
        discogs_url=url,
        notes=_as_str(mapped.get("notes")),
        release_id=release_id,
        sort_artist=sort_artist,
        sort_title=sort_title,
        thumb_url=_as_str(mapped.get("thumb")),
        cover_image_url=_as_str(mapped.get("cover")),
        format_categories=categories,
        source=_as_str(mapped.get("source")) or default_source,
        item_id=item_id,
    )


def _piece_to_format(piece: str) -> Dict[str, Any]:
    qty = ""
    rest = piece.strip()
    qty_match = re.match(r"^(\d+)\s*[x×]\s*(.+)$", rest, re.IGNORECASE)
    if qty_match:
        qty = qty_match.group(1)
        rest = qty_match.group(2).strip()
    parts = [p.strip() for p in rest.split(",") if p.strip()]
    if not parts:
        return {"name": "", "qty": qty, "descriptions": []}
    first = parts[0]
    first_key = re.sub(r"\s+", " ", first.lower())
    if first_key in _KNOWN_FORMAT_NAMES:
        return {"name": first, "qty": qty, "descriptions": parts[1:]}
    blob = rest.lower()
    if re.search(r"\bcd\b", blob) and "vinyl" not in blob:
        return {"name": "CD", "qty": qty, "descriptions": [p for p in parts if p.lower() != "cd"]}
    if "cassette" in blob or blob.strip() in {"tape", "mc"}:
        return {"name": "Cassette", "qty": qty, "descriptions": parts}
    if "box set" in blob or blob.strip() == "box":
        return {"name": "Box Set", "qty": qty, "descriptions": parts}
    if "vinyl" in blob or "lp" in blob or '7"' in blob or '12"' in blob or "45" in blob:
        descs = [p for p in parts if p.lower() != "vinyl"]
        return {"name": "Vinyl", "qty": qty, "descriptions": descs}
    return {"name": "Vinyl", "qty": qty, "descriptions": parts}


def _read_csv_records(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    if not raw.strip():
        raise CollectionImportError("The CSV file is empty.")
    sample = raw[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        if sample.count(";") > sample.count(","):
            delimiter = ";"
    reader = csv.DictReader(raw.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise CollectionImportError("The CSV file has no header row.")
    headers = [_normalize_header(h or "") for h in reader.fieldnames]
    if "artist" not in headers and "title" not in headers:
        raise CollectionImportError(
            "CSV must include Artist and/or Title columns (Spindle export columns work)."
        )
    return [row for row in reader if any((v or "").strip() for v in row.values())]


def _read_json_records(path: Path) -> List[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise CollectionImportError(f"Invalid JSON: {exc}") from exc
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ("rows", "releases", "items", "collection"):
            if isinstance(data.get(key), list):
                records = data[key]
                break
        else:
            raise CollectionImportError(
                "JSON must be a list of albums, or an object with a rows/releases array."
            )
    else:
        raise CollectionImportError("JSON must be a list of albums.")
    if not records:
        raise CollectionImportError("The JSON file has no albums.")
    if not isinstance(records[0], dict):
        raise CollectionImportError("JSON albums must be objects with Artist/Title fields.")
    return records
