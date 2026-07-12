"""Tests for audio preview lookup. Run with: python test_audio_preview.py"""

from unittest.mock import MagicMock, patch

from core.audio_preview import (
    _score_match,
    fetch_discogs_youtube_preview,
    find_audio_preview,
    search_deezer_preview,
    search_itunes_preview,
)


def assert_true(value, msg=""):
    if not value:
        raise AssertionError(msg or f"Expected truthy value, got {value!r}")


def assert_eq(a, b, msg=""):
    if a != b:
        raise AssertionError(msg or f"Expected {b!r}, got {a!r}")


def test_score_match_prefers_album_and_artist():
    score = _score_match(
        "David Bowie",
        "Scary Monsters",
        "David Bowie",
        "Scary Monsters (And Super Creeps)",
    )
    assert_true(score >= 5)


@patch("core.audio_preview.requests.get")
def test_search_itunes_preview_returns_best_match(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "results": [
                {
                    "artistName": "David Bowie",
                    "collectionName": "Scary Monsters (And Super Creeps)",
                    "trackName": "Ashes to Ashes",
                    "previewUrl": "https://example.com/sample.m4a",
                }
            ]
        },
    )
    preview = search_itunes_preview("David Bowie", "Scary Monsters")
    assert_true(preview is not None)
    assert_eq(preview.kind, "stream")
    assert_eq(preview.source, "iTunes")
    assert_true(preview.url.endswith("sample.m4a"))


@patch("core.audio_preview.requests.get")
def test_search_deezer_preview_returns_track_preview(mock_get):
    def fake_get(url, timeout=10):
        if "search/album" in url:
            return MagicMock(
                status_code=200,
                json=lambda: {
                    "data": [
                        {
                            "id": 123,
                            "title": "Scary Monsters",
                            "artist": {"name": "David Bowie"},
                        }
                    ]
                },
            )
        return MagicMock(
            status_code=200,
            json=lambda: {
                "data": [
                    {"title": "Ashes to Ashes", "preview": "https://example.com/deezer.mp3"}
                ]
            },
        )

    mock_get.side_effect = fake_get
    preview = search_deezer_preview("David Bowie", "Scary Monsters")
    assert_true(preview is not None)
    assert_eq(preview.source, "Deezer")
    assert_true(preview.url.endswith("deezer.mp3"))


@patch("core.audio_preview.api_get")
def test_fetch_discogs_youtube_preview(mock_api_get):
    mock_api_get.return_value = MagicMock(
        json=lambda: {
            "videos": [
                {
                    "title": "Album preview",
                    "uri": "https://www.youtube.com/watch?v=abc123",
                    "embed": True,
                }
            ]
        }
    )
    preview = fetch_discogs_youtube_preview(12345, headers={"User-Agent": "test"})
    assert_true(preview is not None)
    assert_eq(preview.kind, "youtube")
    assert_eq(preview.source, "Discogs")


@patch("core.audio_preview.fetch_discogs_youtube_preview")
@patch("core.audio_preview.search_deezer_preview", return_value=None)
@patch("core.audio_preview.search_itunes_preview", return_value=None)
def test_find_audio_preview_falls_back_to_discogs(mock_itunes, mock_deezer, mock_discogs):
    mock_discogs.return_value = MagicMock(
        kind="youtube",
        url="https://youtube.com/x",
        title="Vid",
        source="Discogs",
    )
    preview = find_audio_preview("Artist", "Album", release_id=99, headers={"User-Agent": "test"})
    assert_true(preview is not None)
    assert_eq(preview.kind, "youtube")
    mock_discogs.assert_called_once()


def main():
    test_score_match_prefers_album_and_artist()
    test_search_itunes_preview_returns_best_match()
    test_search_deezer_preview_returns_track_preview()
    test_fetch_discogs_youtube_preview()
    test_find_audio_preview_falls_back_to_discogs()
    print("All audio preview tests passed.")


if __name__ == "__main__":
    main()
