"""
Format filter constants and row filtering for the Auto-Sort GUI.

Keys on ReleaseRow.format_categories (from core.sorting.detect_format_categories)
match FORMAT_FILTERS except "everything", which means no category restriction.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Set, TypeVar

T = TypeVar("T")

# Display order for settings checkboxes: (category_key, label).
FORMAT_FILTERS: List[tuple[str, str]] = [
  ("everything", "Everything"),
  ("vinyl", "All Vinyl"),
  ("lp", "Vinyl LP"),
  ("vinyl45", "Vinyl 45s"),
  ("cd", "CD"),
  ("cassette", "Cassette"),
  ("boxset", "Box Set"),
]

# Default selection preserves the previous LP-only view.
DEFAULT_FORMAT_SELECTION: List[str] = ["lp"]

VALID_FORMAT_KEYS: Set[str] = {key for key, _ in FORMAT_FILTERS}


def parse_saved_formats(saved: object) -> List[str]:
  """Validate formats list from config; fall back to DEFAULT_FORMAT_SELECTION."""
  if not isinstance(saved, list) or not saved:
    return list(DEFAULT_FORMAT_SELECTION)
  keys = [k for k in saved if isinstance(k, str) and k in VALID_FORMAT_KEYS]
  return keys if keys else list(DEFAULT_FORMAT_SELECTION)


def selected_format_keys(checked: Iterable[str]) -> List[str]:
  """Return format keys that are currently selected (for persistence)."""
  return list(checked)


def filter_rows_by_format(rows: Sequence[T], selected: Set[str]) -> List[T]:
  """
  Filter rows to those matching selected format checkboxes.

  Empty selection or "everything" returns all rows. Otherwise a row is kept
  if its format_categories intersect selected (union semantics).
  """
  if not selected or "everything" in selected:
    return list(rows)
  return [
    r
    for r in rows
    if getattr(r, "format_categories", frozenset()) & selected
  ]
