"""Output formatting and export functions for Discogs vinyl sorter.

This module contains all the functions for formatting and writing output files
in various formats (TXT, CSV, JSON).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.models import ReleaseRow


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
