from dataclasses import dataclass, field
from typing import Optional

SOURCE_DISCOGS = "discogs"
SOURCE_LOCAL = "local"
LOCAL_USERNAME = "Imported"


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
    format_categories: frozenset = field(default_factory=frozenset)
    source: str = SOURCE_DISCOGS
    item_id: str = ""

    def key(self) -> str:
        """Stable identity for manual order, thumbnails, and caches."""
        if self.item_id:
            return self.item_id
        if self.release_id is not None:
            return f"discogs:{self.release_id}"
        return ""

    def cache_id(self) -> str:
        """Filesystem-safe cache key. Discogs rows keep numeric IDs for existing thumbs."""
        if self.release_id is not None:
            return str(self.release_id)
        if self.item_id:
            return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in self.item_id)
        return ""

    def artwork_url(self) -> str:
        return self.cover_image_url or self.thumb_url


@dataclass
class BuildResult:
    username: str
    rows_sorted: list[ReleaseRow]
    lines: list[str]
