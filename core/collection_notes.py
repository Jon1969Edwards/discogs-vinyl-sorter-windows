"""Discogs collection notes helpers, including the spindle-genre sync marker.

Genre corrections are stored as a `spindle-genre:` line on a collection notes
field so desktop and phone pick them up on the next Discogs refresh.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Tuple

MARKER_PREFIX = "spindle-genre:"


def extract_spindle_genre(text: str) -> Optional[str]:
    if not text:
        return None
    for line in str(text).splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(MARKER_PREFIX):
            return stripped.split(":", 1)[1].strip()
    return None


def strip_spindle_genre(text: str) -> str:
    if not text:
        return ""
    lines = [
        ln
        for ln in str(text).splitlines()
        if not ln.strip().lower().startswith(MARKER_PREFIX)
    ]
    return "\n".join(lines).strip()


def inject_spindle_genre(user_notes: str, genres_text: Optional[str]) -> str:
    base = strip_spindle_genre(user_notes or "")
    if genres_text is None:
        return base
    line = f"{MARKER_PREFIX} {str(genres_text).strip()}"
    return f"{base}\n{line}" if base else line


def iter_note_fields(notes: Any) -> List[Tuple[Optional[int], str]]:
    if notes is None or notes == "":
        return []
    if isinstance(notes, str):
        return [(None, notes)]
    if isinstance(notes, list):
        out: List[Tuple[Optional[int], str]] = []
        for entry in notes:
            if isinstance(entry, str):
                out.append((None, entry))
            elif isinstance(entry, dict):
                fid = entry.get("field_id")
                try:
                    field_id = int(fid) if fid is not None else None
                except (TypeError, ValueError):
                    field_id = None
                out.append((field_id, str(entry.get("value") or "")))
        return out
    if isinstance(notes, dict) and "value" in notes:
        fid = notes.get("field_id")
        try:
            field_id = int(fid) if fid is not None else None
        except (TypeError, ValueError):
            field_id = None
        return [(field_id, str(notes.get("value") or ""))]
    return [(None, str(notes))]


def format_display_notes(notes: Any) -> str:
    parts = []
    for _, val in iter_note_fields(notes):
        stripped = strip_spindle_genre(val)
        if stripped:
            parts.append(stripped)
    return "\n".join(parts)


def extract_from_notes(notes: Any) -> Tuple[Optional[str], Optional[int]]:
    for field_id, val in iter_note_fields(notes):
        genre = extract_spindle_genre(val)
        if genre is not None:
            return genre, field_id
    return None, None


def value_for_field(notes: Any, field_id: Optional[int]) -> str:
    if field_id is None:
        if isinstance(notes, str):
            return notes
        return ""
    for fid, val in iter_note_fields(notes):
        if fid == field_id:
            return val
    if isinstance(notes, str):
        return notes
    return ""


def pick_notes_field_id(fields: Iterable[dict], notes: Any = None) -> Optional[int]:
    field_list = [f for f in fields if isinstance(f, dict)]
    by_id = {f.get("id"): f for f in field_list}
    genre, marked_id = extract_from_notes(notes)
    if genre is not None and marked_id is not None:
        meta = by_id.get(marked_id) or {}
        if (meta.get("type") or "").lower() != "dropdown":
            return marked_id
    for field in field_list:
        name = (field.get("name") or "").lower()
        typ = (field.get("type") or "").lower()
        if "spindle" in name and typ != "dropdown":
            return field.get("id")
    for field in field_list:
        name = (field.get("name") or "").lower()
        typ = (field.get("type") or "").lower()
        if name == "notes" and typ == "textarea":
            return field.get("id")
    for field in field_list:
        if (field.get("type") or "").lower() == "textarea":
            return field.get("id")
    return None


def attach_collection_notes(row: Any, item: dict) -> None:
    iid = item.get("instance_id")
    try:
        row.instance_id = int(iid) if iid not in (None, "") else None
    except (TypeError, ValueError):
        row.instance_id = None
    folder = item.get("folder_id")
    try:
        folder_id = int(folder) if folder not in (None, "") else 1
    except (TypeError, ValueError):
        folder_id = 1
    row.folder_id = 1 if folder_id == 0 else folder_id
    notes = item.get("notes")
    row.collection_notes = notes
    row.notes = format_display_notes(notes)
    genre, field_id = extract_from_notes(notes)
    row.spindle_genre_edit = genre or ""
    row.notes_field_id = field_id
