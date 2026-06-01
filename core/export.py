"""Output formatting and export functions for Discogs vinyl sorter.

This module contains all the functions for formatting and writing output files
in various formats (TXT, CSV, JSON).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from core.models import ReleaseRow

DividerMode = Literal["none", "letter", "abc"]

SHELF_A_RANGE = "A–H"
SHELF_B_RANGE = "I–P"
SHELF_C_RANGE = "Q–Z"

SHELF_DIVIDER_TITLES = {
    "A": f"SHELF A ({SHELF_A_RANGE})",
    "B": f"SHELF B ({SHELF_B_RANGE})",
    "C": f"SHELF C ({SHELF_C_RANGE})",
}


def resolve_divider_mode(dividers: bool = False, divider_mode: Optional[str] = None) -> DividerMode:
    """Resolve divider mode from legacy bool and/or explicit mode string."""
    if divider_mode in ("none", "letter", "abc"):
        return divider_mode  # type: ignore[return-value]
    return "letter" if dividers else "none"


def sort_letter_from_row(r: ReleaseRow) -> str:
    sa = r.sort_artist.strip()
    first = sa[0].upper() if sa else "#"
    if not first.isalpha():
        first = "#"
    return first


def sort_letter_to_shelf(letter: str) -> str:
    """Map first sort letter to physical shelf A, B, or C (for printed dividers)."""
    ch = (letter or "#")[0].upper()
    if not ch.isalpha():
        ch = "#"
    if ch == "#" or ch <= "H":
        return "A"
    if ch <= "P":
        return "B"
    return "C"


def get_divider_line(
    r: ReleaseRow,
    current: Optional[str],
    mode: DividerMode,
) -> Tuple[Optional[str], Optional[str]]:
    if mode == "none":
        return current, None
    if mode == "letter":
        first = sort_letter_from_row(r)
        if current != first:
            return first, f"=== {first} ==="
        return current, None
    # abc: one divider per physical shelf section
    letter = sort_letter_from_row(r)
    shelf = sort_letter_to_shelf(letter)
    if current != shelf:
        return shelf, f"=== {SHELF_DIVIDER_TITLES[shelf]} ==="
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
    divider_mode: Optional[str] = None,
    align: bool = False,
    show_country: bool = False,
    show_price: bool = False,
) -> List[str]:
    """Return the lines that would appear in the TXT output.

    Used by both CLI writer and GUI preview to avoid duplication.
    divider_mode: none | letter (=== A ===) | abc (=== SHELF A (A–H) ===).
    """
    mode = resolve_divider_mode(dividers, divider_mode)
    artist_width = max((len(r.artist_display) for r in rows), default=0) if align else 0
    title_width = max((len(r.title) for r in rows), default=0) if align else 0

    lines: List[str] = []
    current_div: Optional[str] = None
    for r in rows:
        current_div, div_line = get_divider_line(r, current_div, mode)
        if div_line:
            lines.append(div_line)
        lines.append(format_txt_line(r, artist_width, title_width, align, show_country, show_price))
    return lines


def write_txt(
    rows: List[ReleaseRow],
    out_path: Path,
    dividers: bool = False,
    divider_mode: Optional[str] = None,
    align: bool = False,
    show_country: bool = False,
    show_price: bool = False,
) -> None:
    lines = generate_txt_lines(
        rows,
        dividers=dividers,
        divider_mode=divider_mode,
        align=align,
        show_country=show_country,
        show_price=show_price,
    )
    with out_path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def write_json(rows: List[ReleaseRow], out_path: Path) -> None:
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
