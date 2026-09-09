"""Push/pull genre edits through Discogs collection notes."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.api import API_BASE, api_get, api_post
from core.collection_notes import (
    inject_spindle_genre,
    pick_notes_field_id,
    value_for_field,
)
from core.genre_overrides import GenreOverrides, _normalize_override_key
from core.models import UNKNOWN_GENRE, ReleaseRow
from core.sorting import parse_genre_list, primary_genre

_fields_cache: Dict[str, List[dict]] = {}


def get_collection_fields(
    username: str,
    *,
    headers: Optional[dict] = None,
    session: Any = None,
) -> List[dict]:
    cached = _fields_cache.get(username)
    if cached is not None:
        return cached
    url = f"{API_BASE}/users/{username}/collection/fields"
    data = api_get(url, headers=headers, session=session).json()
    fields = data.get("fields") or []
    if not isinstance(fields, list):
        fields = []
    _fields_cache[username] = fields
    return fields


def pull_genre_overrides(rows: Iterable[ReleaseRow], store: GenreOverrides) -> int:
    incoming: Dict[str, dict] = {}
    for row in rows:
        text = (getattr(row, "spindle_genre_edit", "") or "").strip()
        if not text:
            continue
        key = row.key() if hasattr(row, "key") else ""
        if not key:
            continue
        parsed = parse_genre_list(text)
        incoming[_normalize_override_key(key)] = {
            "genre": primary_genre(parsed) if parsed else UNKNOWN_GENRE,
            "genres": list(parsed),
        }
    if not incoming:
        return 0
    return store.merge_overrides(incoming)


def push_genre_edit(
    row: ReleaseRow,
    *,
    username: str,
    headers: Optional[dict] = None,
    session: Any = None,
    genres_text: Optional[str],
) -> bool:
    release_id = getattr(row, "release_id", None)
    instance_id = getattr(row, "instance_id", None)
    if not release_id or not instance_id:
        return False
    if not str(getattr(row, "item_id", "") or "").startswith("discogs:"):
        return False
    fields = get_collection_fields(username, headers=headers, session=session)
    notes = getattr(row, "collection_notes", None)
    field_id = pick_notes_field_id(fields, notes)
    if not field_id:
        return False
    current = value_for_field(notes, field_id)
    new_val = inject_spindle_genre(current, genres_text)
    folder_id = getattr(row, "folder_id", None) or 1
    if folder_id == 0:
        folder_id = 1
    url = (
        f"{API_BASE}/users/{username}/collection/folders/{folder_id}"
        f"/releases/{int(release_id)}/instances/{int(instance_id)}/fields/{int(field_id)}"
    )
    api_post(url, headers=headers, session=session, params={"value": new_val})
    row.spindle_genre_edit = (genres_text or "").strip()
    return True


def push_missing_genre_overrides(
    rows: Iterable[ReleaseRow],
    store: GenreOverrides,
    *,
    username: str,
    headers: Optional[dict] = None,
    session: Any = None,
    log: Optional[Any] = None,
) -> int:
    pushed = 0
    for row in rows:
        if not store.has(row):
            continue
        if (getattr(row, "spindle_genre_edit", "") or "").strip():
            continue
        entry = store.get(row) or {}
        genres = entry.get("genres") or []
        genres_text = "; ".join(genres) if genres else (entry.get("genre") or "")
        try:
            if push_genre_edit(
                row,
                username=username,
                headers=headers,
                session=session,
                genres_text=genres_text,
            ):
                pushed += 1
        except Exception as exc:
            if log:
                log(f"Genre sync skipped for {getattr(row, 'title', '')}: {exc}")
    return pushed


def sync_genre_overrides_with_discogs(
    rows: List[ReleaseRow],
    store: GenreOverrides,
    *,
    username: str,
    headers: Optional[dict] = None,
    session: Any = None,
    log: Optional[Any] = None,
) -> None:
    pulled = pull_genre_overrides(rows, store)
    if pulled and log:
        log(f"Loaded {pulled} genre edit(s) from Discogs.")
    pushed = push_missing_genre_overrides(
        rows,
        store,
        username=username,
        headers=headers,
        session=session,
        log=log,
    )
    if pushed and log:
        log(f"Saved {pushed} genre edit(s) to Discogs.")
