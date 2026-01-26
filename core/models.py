from dataclasses import dataclass
from typing import Optional

@dataclass
class ReleaseRow:
    artist_display: str
    title: str
    year: Optional[int]
    label: str
    catno: str
    country: str
    format_str: str
    discogs_url: str
    notes: str
    release_id: Optional[int] = None
    master_id: Optional[int] = None
    sort_artist: str = ""
    sort_title: str = ""
    median_price: Optional[float] = None
    lowest_price: Optional[float] = None
    num_for_sale: Optional[int] = None
    price_currency: str = ""
    thumb_url: str = ""
    cover_image_url: str = ""

@dataclass
class BuildResult:
    username: str
    rows_sorted: list[ReleaseRow]
    lines: list[str]
