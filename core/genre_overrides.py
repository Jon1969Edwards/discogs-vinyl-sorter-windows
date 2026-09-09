"""User genre corrections that survive Discogs refreshes.

Stored under the user data directory as genre_overrides.json, keyed by
ReleaseRow.key() (discogs:id or local:hash).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.models import UNKNOWN_GENRE, ReleaseRow
from core.paths import migrate_user_file
from core.sorting import parse_genre_list, primary_genre

GENRE_OVERRIDES_FILE = migrate_user_file("genre_overrides.json")


def override_lookup_keys(row: ReleaseRow) -> List[str]:
    keys: List[str] = []
    item_id = (getattr(row, "item_id", "") or "").strip()
    if item_id:
        keys.append(item_id)
    rid = getattr(row, "release_id", None)
    if rid is not None:
        keys.append(f"discogs:{rid}")
        keys.append(str(rid))
    return keys


def parse_overrides_payload(data: object) -> Dict[str, dict]:
    """Parse genre_overrides.json or a Spindle collection JSON into override entries."""
    if isinstance(data, list):
        return _overrides_from_rows(data)
    if not isinstance(data, dict):
        raise ValueError("Not a JSON object or array.")
    raw = data.get("overrides")
    if isinstance(raw, dict):
        return _normalize_override_map(raw)
    rows = data.get("rows")
    if isinstance(rows, list):
        return _overrides_from_rows(rows)
    raise ValueError("Unrecognized genre edits file.")


def _normalize_override_key(key: str) -> str:
    text = str(key).strip()
    if text.isdigit():
        return f"discogs:{text}"
    return text


def _entry_from_value(raw: object) -> Optional[dict]:
    if isinstance(raw, str):
        parsed = parse_genre_list(raw)
        return {"genre": primary_genre(parsed) if parsed else UNKNOWN_GENRE, "genres": list(parsed)}
    if isinstance(raw, dict):
        parsed = parse_genre_list(raw.get("genres") or raw.get("genre"))
        return {"genre": primary_genre(parsed) if parsed else UNKNOWN_GENRE, "genres": list(parsed)}
    return None


def _normalize_override_map(raw: dict) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for key, value in raw.items():
        entry = _entry_from_value(value)
        if entry is None:
            continue
        out[_normalize_override_key(str(key))] = entry
    return out


def _overrides_from_rows(rows: list) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("release_id") or row.get("releaseId")
        item_id = str(row.get("item_id") or "").strip()
        if not item_id and rid is not None and str(rid).strip():
            item_id = f"discogs:{rid}"
        if not item_id:
            continue
        genre_val = row.get("genres") or row.get("genre")
        if genre_val in (None, "", []):
            continue
        entry = _entry_from_value({"genre": row.get("genre"), "genres": row.get("genres")})
        if entry:
            out[_normalize_override_key(item_id)] = entry
    return out


class GenreOverrides:
    """Persistent primary-genre edits for collection rows."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or GENRE_OVERRIDES_FILE
        self._data: dict = {"version": 1, "overrides": {}}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and loaded.get("version") == 1:
                    overrides = loaded.get("overrides") or {}
                    if isinstance(overrides, dict):
                        self._data["overrides"] = overrides
        except Exception:
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _overrides(self) -> Dict[str, dict]:
        return self._data.setdefault("overrides", {})

    def get(self, row: ReleaseRow) -> Optional[dict]:
        stored = self._overrides()
        for key in override_lookup_keys(row):
            entry = stored.get(key)
            if isinstance(entry, dict):
                return entry
        return None

    def has(self, row: ReleaseRow) -> bool:
        return self.get(row) is not None

    def set_for_row(self, row: ReleaseRow, genres_text: str) -> bool:
        """Save an override and apply it to the row. Returns False if the row has no id."""
        key = row.key() if hasattr(row, "key") else ""
        if not key:
            return False
        parsed = parse_genre_list(genres_text)
        genre = primary_genre(parsed) if parsed else UNKNOWN_GENRE
        row.capture_source_genre()
        row.genre = genre
        row.genres = parsed
        self._overrides()[key] = {
            "genre": genre,
            "genres": list(parsed),
        }
        self._save()
        return True

    def clear_for_row(self, row: ReleaseRow) -> bool:
        """Remove the override and restore the Discogs/import genre."""
        stored = self._overrides()
        removed = False
        for key in override_lookup_keys(row):
            if key in stored:
                del stored[key]
                removed = True
        if removed:
            self._save()
        row.restore_source_genre()
        return removed

    def apply_to_row(self, row: ReleaseRow) -> bool:
        row.capture_source_genre()
        entry = self.get(row)
        if not entry:
            return False
        parsed = parse_genre_list(entry.get("genres") or entry.get("genre"))
        row.genre = primary_genre(parsed) if parsed else UNKNOWN_GENRE
        row.genres = parsed
        return True

    def apply_to_rows(self, rows: Iterable[ReleaseRow]) -> int:
        count = 0
        for row in rows:
            if self.apply_to_row(row):
                count += 1
        return count

    def to_dict(self) -> dict:
        return {"version": 1, "overrides": dict(self._overrides())}

    def count(self) -> int:
        return len(self._overrides())

    def export_to_path(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def merge_overrides(self, incoming: Dict[str, dict]) -> int:
        stored = self._overrides()
        added = 0
        for key, entry in incoming.items():
            if not isinstance(entry, dict):
                continue
            stored[_normalize_override_key(key)] = {
                "genre": entry.get("genre") or UNKNOWN_GENRE,
                "genres": list(entry.get("genres") or []),
            }
            added += 1
        if added:
            self._save()
        return added

    def import_from_path(self, path: Path) -> int:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return self.merge_overrides(parse_overrides_payload(data))


def apply_genre_overrides(rows: List[ReleaseRow], store: GenreOverrides | None = None) -> int:
    """Apply saved genre edits to freshly loaded/fetched rows."""
    return (store or GenreOverrides()).apply_to_rows(rows)
