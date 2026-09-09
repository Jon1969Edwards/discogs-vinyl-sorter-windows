# Genre override persistence. Run: python test_genre_overrides.py

from __future__ import annotations

import tempfile
from pathlib import Path

from core.genre_overrides import GenreOverrides, apply_genre_overrides
from core.models import UNKNOWN_GENRE, ReleaseRow
from core.sorting import sort_rows


def assert_eq(a, b, msg: str = ""):
    if a != b:
        raise AssertionError(msg or f"Expected {b!r}, got {a!r}")


def _row(release_id: int, genre: str, artist="Artist", title="Album") -> ReleaseRow:
    return ReleaseRow(
        artist_display=artist,
        title=title,
        year=1970,
        label="",
        catno="",
        country="",
        format_str="",
        discogs_url="",
        notes="",
        release_id=release_id,
        item_id=f"discogs:{release_id}",
        sort_artist=artist.lower(),
        sort_title=title.lower(),
        genre=genre,
        genres=(genre,) if genre else (),
        source_genre=genre,
        source_genres=(genre,) if genre else (),
    )


def main():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "genre_overrides.json"
        store = GenreOverrides(path)

        jazz = _row(1, "Jazz", artist="Miles")
        rock = _row(2, "Rock", artist="Beatles")
        assert_eq(store.has(jazz), False)
        assert_eq(store.set_for_row(jazz, "Funk / Soul"), True)
        assert_eq(jazz.genre, "Funk / Soul")
        assert_eq(jazz.genres, ("Funk / Soul",))
        assert_eq(jazz.source_genre, "Jazz")
        assert_eq(store.has(jazz), True)

        store.set_for_row(jazz, "Rock; Pop")
        assert_eq(jazz.genre, "Rock")
        assert_eq(jazz.genres, ("Rock", "Pop"))

        reloaded = GenreOverrides(path)
        fresh = _row(1, "Jazz", artist="Miles")
        n = apply_genre_overrides([fresh, rock], store=reloaded)
        assert_eq(n, 1)
        assert_eq(fresh.genre, "Rock")
        assert_eq(fresh.genres, ("Rock", "Pop"))
        assert_eq(fresh.source_genre, "Jazz")
        assert_eq(rock.genre, "Rock")

        reloaded.clear_for_row(fresh)
        assert_eq(fresh.genre, "Jazz")
        assert_eq(reloaded.has(fresh), False)
        again = _row(1, "Jazz", artist="Miles")
        assert_eq(apply_genre_overrides([again], store=reloaded), 0)
        assert_eq(again.genre, "Jazz")

        unknown = _row(3, "Jazz", artist="Mystery")
        store.set_for_row(unknown, "")
        assert_eq(unknown.genre, UNKNOWN_GENRE)
        by_genre = sort_rows([jazz, unknown], "normal", sort_by="genre")
        assert_eq(by_genre[-1].artist_display, "Mystery")
        assert_eq(by_genre[-1].genre, UNKNOWN_GENRE)

        no_id = ReleaseRow(
            artist_display="X",
            title="Y",
            year=None,
            label="",
            catno="",
            country="",
            format_str="",
            discogs_url="",
            notes="",
        )
        assert_eq(store.set_for_row(no_id, "Rock"), False)

        payload = {
            "version": 1,
            "overrides": {
                "19000885": {"genre": "Punk/Hardcore, Reggae", "genres": ["Punk/Hardcore, Reggae"]},
                "discogs:6057905": {"genre": "Indie", "genres": ["Indie"]},
            },
        }
        from core.genre_overrides import parse_overrides_payload
        parsed = parse_overrides_payload(payload)
        assert_eq("discogs:19000885" in parsed, True)
        assert_eq(parsed["discogs:6057905"]["genre"], "Indie")
        other = Path(td) / "incoming.json"
        store.export_to_path(other)
        incoming = GenreOverrides(Path(td) / "empty.json")
        added = incoming.import_from_path(other)
        assert_eq(added >= 1, True)
        rows_json = [
            {"release_id": 6171913, "genre": "Oi!/Streetpunk", "genres": ["Oi!/Streetpunk"]},
        ]
        from_rows = parse_overrides_payload(rows_json)
        assert_eq(from_rows["discogs:6171913"]["genre"], "Oi!/Streetpunk")
        merged = incoming.merge_overrides(from_rows)
        assert_eq(merged, 1)
        fresh_oi = _row(6171913, "Rock")
        apply_genre_overrides([fresh_oi], store=incoming)
        assert_eq(fresh_oi.genre, "Oi!/Streetpunk")

    print("All genre override assertions passed.")


if __name__ == "__main__":
    main()
