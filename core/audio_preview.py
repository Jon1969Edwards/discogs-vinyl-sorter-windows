"""Find playable audio previews for album info popups."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Literal, Optional

try:
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    requests = None  # type: ignore

from core.api import API_BASE, api_get

PreviewKind = Literal["stream", "youtube"]


@dataclass(frozen=True)
class AudioPreview:
    """A playable preview for an album."""

    kind: PreviewKind
    url: str
    title: str
    source: str


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _score_match(artist: str, album: str, result_artist: str, result_album: str) -> int:
    artist_norm = _normalize(artist)
    album_norm = _normalize(album)
    result_artist_norm = _normalize(result_artist or "")
    result_album_norm = _normalize(result_album or "")

    score = 0
    if artist_norm and artist_norm in result_artist_norm:
        score += 2
    if album_norm and album_norm in result_album_norm:
        score += 3
    if album_norm and result_album_norm.startswith(album_norm[: min(len(album_norm), 12)]):
        score += 1
    return score


def search_itunes_preview(artist: str, album: str) -> Optional[AudioPreview]:
    """Search iTunes for a ~30 second MP3 preview."""
    if requests is None:
        return None

    term = urllib.parse.quote(f"{artist} {album}")
    url = f"https://itunes.apple.com/search?term={term}&entity=song&limit=25"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except Exception:
        return None

    best: Optional[AudioPreview] = None
    best_score = 0
    for item in results:
        preview_url = item.get("previewUrl")
        if not preview_url:
            continue
        score = _score_match(
            artist,
            album,
            item.get("artistName") or "",
            item.get("collectionName") or "",
        )
        if score > best_score:
            best_score = score
            track = item.get("trackName") or "Sample"
            best = AudioPreview(
                kind="stream",
                url=preview_url,
                title=track,
                source="iTunes",
            )

    if best_score == 0 and results:
        item = next((r for r in results if r.get("previewUrl")), None)
        if item:
            best = AudioPreview(
                kind="stream",
                url=item["previewUrl"],
                title=item.get("trackName") or "Sample",
                source="iTunes",
            )
    return best


def search_deezer_preview(artist: str, album: str) -> Optional[AudioPreview]:
    """Search Deezer for a ~30 second MP3 preview."""
    if requests is None:
        return None

    query = urllib.parse.quote(f"{artist} {album}")
    try:
        resp = requests.get(f"https://api.deezer.com/search/album?q={query}", timeout=10)
        resp.raise_for_status()
        albums = resp.json().get("data") or []
    except Exception:
        return None

    if not albums:
        return None

    best_album = max(
        albums,
        key=lambda item: _score_match(
            artist,
            album,
            (item.get("artist") or {}).get("name") or "",
            item.get("title") or "",
        ),
    )
    album_id = best_album.get("id")
    if not album_id:
        return None

    try:
        tracks_resp = requests.get(f"https://api.deezer.com/album/{album_id}/tracks", timeout=10)
        tracks_resp.raise_for_status()
        tracks = tracks_resp.json().get("data") or []
    except Exception:
        return None

    for track in tracks:
        preview_url = track.get("preview")
        if preview_url:
            return AudioPreview(
                kind="stream",
                url=preview_url,
                title=track.get("title") or "Sample",
                source="Deezer",
            )
    return None


def fetch_discogs_youtube_preview(
    release_id: int,
    headers: Optional[dict] = None,
    session=None,
) -> Optional[AudioPreview]:
    """Return the first embeddable YouTube video linked on a Discogs release."""
    if not release_id:
        return None

    url = f"{API_BASE}/releases/{release_id}"
    try:
        resp = api_get(url, headers=headers, session=session)
        data = resp.json()
    except Exception:
        return None

    for video in data.get("videos") or []:
        if not video.get("embed", True):
            continue
        uri = video.get("uri") or ""
        if "youtube.com" in uri or "youtu.be" in uri:
            return AudioPreview(
                kind="youtube",
                url=uri,
                title=video.get("title") or "YouTube video",
                source="Discogs",
            )
    return None


def find_audio_preview(
    artist: str,
    album: str,
    release_id: Optional[int] = None,
    headers: Optional[dict] = None,
    session=None,
) -> Optional[AudioPreview]:
    """Find the best available preview: iTunes, Deezer, then Discogs YouTube."""
    for finder in (search_itunes_preview, search_deezer_preview):
        preview = finder(artist, album)
        if preview:
            return preview

    if release_id:
        return fetch_discogs_youtube_preview(release_id, headers=headers, session=session)
    return None
