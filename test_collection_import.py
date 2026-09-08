# Import CSV/JSON collections without Discogs. Run: python test_collection_import.py

from __future__ import annotations

import tempfile
from pathlib import Path

from core.collection_import import (
    CollectionImportError,
    detect_format_categories_from_str,
    load_collection_file,
    parse_discogs_release_id,
    rows_from_records,
)
from core.export import write_csv, write_json
from core.local_collection import LocalCollectionStore
from core.models import SOURCE_LOCAL, LOCAL_USERNAME, ReleaseRow
from core.build_service import AutoConfig, build_once
from core.sorting import sort_rows


def assert_eq(a, b, msg: str = ""):
    if a != b:
        raise AssertionError(msg or f"Expected {b!r}, got {a!r}")


def assert_true(cond, msg: str = ""):
    if not cond:
        raise AssertionError(msg or "Expected true")


def _row(**kwargs) -> ReleaseRow:
    defaults = dict(
        artist_display="Miles Davis",
        title="Kind of Blue",
        year=1959,
        label="Columbia",
        catno="CL 1355",
        country="US",
        format_str="Vinyl, LP, Album",
        discogs_url="https://www.discogs.com/release/12345",
        notes="",
        release_id=12345,
        sort_artist="davis, miles",
        sort_title="kind of blue",
        format_categories=frozenset({"lp", "vinyl"}),
        source="discogs",
        item_id="discogs:12345",
    )
    defaults.update(kwargs)
    return ReleaseRow(**defaults)


def test_parse_discogs_release_id():
    assert_eq(parse_discogs_release_id("https://www.discogs.com/release/12345"), 12345)
    assert_eq(parse_discogs_release_id("https://www.discogs.com/release/12345-Miles-Davis-Kind-Of-Blue"), 12345)
    assert_eq(parse_discogs_release_id("https://api.discogs.com/releases/99"), 99)
    assert_eq(parse_discogs_release_id("12345"), 12345)
    assert_eq(parse_discogs_release_id(""), None)


def test_format_categories_from_str():
    lp = detect_format_categories_from_str("Vinyl, LP, Album")
    assert_true("lp" in lp and "vinyl" in lp, "Vinyl LP album should tag lp+vinyl")

    cd = detect_format_categories_from_str("CD, Album")
    assert_eq(sorted(cd), ["cd"])

    single = detect_format_categories_from_str('Vinyl, 7", 45 RPM, Single')
    assert_true("vinyl45" in single and "vinyl" in single)

    cassette = detect_format_categories_from_str("Cassette, Album")
    assert_eq(sorted(cassette), ["cassette"])

    loose_lp = detect_format_categories_from_str("LP")
    assert_true("lp" in loose_lp, "Bare 'LP' should still count as vinyl LP")


def test_csv_round_trip(tmp: Path):
    src = [_row(), _row(artist_display="The Beatles", title="Abbey Road", year=1969, catno="PCS 7088", release_id=None, discogs_url="", item_id="", source=SOURCE_LOCAL, format_str="Vinyl, LP, Album")]
    csv_path = tmp / "out.csv"
    write_csv(src, csv_path)
    loaded = load_collection_file(csv_path)
    assert_eq(len(loaded), 2)
    assert_eq(loaded[0].artist_display, "Miles Davis")
    assert_eq(loaded[0].release_id, 12345)
    assert_eq(loaded[0].title, "Kind of Blue")
    assert_true("lp" in loaded[1].format_categories)
    assert_true(loaded[1].item_id.startswith("local:"))


def test_json_round_trip(tmp: Path):
    src = [_row()]
    json_path = tmp / "out.json"
    write_json(src, json_path)
    loaded = load_collection_file(json_path)
    assert_eq(len(loaded), 1)
    assert_eq(loaded[0].catno, "CL 1355")
    assert_eq(loaded[0].release_id, 12345)


def test_spreadsheet_headers(tmp: Path):
    csv_path = tmp / "sheet.csv"
    csv_path.write_text(
        "Artist,Title,Year,Format\n"
        "David Bowie,Low,1977,LP\n"
        "Talking Heads,Remain in Light,1980,\"Vinyl, LP, Album\"\n",
        encoding="utf-8",
    )
    # The third row has extra commas — DictReader will still parse Artist/Title/Year
    loaded = load_collection_file(csv_path)
    assert_true(any(r.artist_display == "David Bowie" for r in loaded))
    bowie = next(r for r in loaded if r.artist_display == "David Bowie")
    assert_true("lp" in bowie.format_categories)


def test_empty_and_bad_files(tmp: Path):
    empty = tmp / "empty.csv"
    empty.write_text("", encoding="utf-8")
    try:
        load_collection_file(empty)
        raise AssertionError("empty CSV should fail")
    except CollectionImportError:
        pass

    no_headers = tmp / "nohead.csv"
    no_headers.write_text("foo,bar\n1,2\n", encoding="utf-8")
    try:
        load_collection_file(no_headers)
        raise AssertionError("CSV without Artist/Title should fail")
    except CollectionImportError:
        pass

    bad_json = tmp / "bad.json"
    bad_json.write_text("{}", encoding="utf-8")
    try:
        load_collection_file(bad_json)
        raise AssertionError("empty JSON object should fail")
    except CollectionImportError:
        pass


def test_local_store_and_build_once(tmp: Path):
    store = LocalCollectionStore(tmp / "local_collection.json")
    rows = [
        _row(format_categories=frozenset({"lp", "vinyl"})),
        _row(
            artist_display="Radiohead",
            title="OK Computer",
            year=1997,
            format_str="CD, Album",
            format_categories=frozenset({"cd"}),
            release_id=None,
            discogs_url="",
            item_id="local:abc",
            source=SOURCE_LOCAL,
        ),
    ]
    store.save_rows(rows, imported_from="test.csv")
    assert_eq(store.count(), 2)
    reloaded = store.load_rows()
    assert_eq(len(reloaded), 2)

    logs: list[str] = []
    cfg = AutoConfig(
        token="",
        user_agent="test",
        output_dir=str(tmp),
        per_page=50,
        write_json=False,
        poll_seconds=30,
        collection_source=SOURCE_LOCAL,
        formats=["everything"],
    )
    result = build_once(cfg, logs.append, local_store=store)
    assert_eq(result.username, LOCAL_USERNAME)
    assert_eq(len(result.rows_sorted), 2)
    assert_true(any("Imported collection" in m for m in logs))

    cfg.formats = ["lp"]
    lp_only = build_once(cfg, logs.append, local_store=store)
    assert_eq(len(lp_only.rows_sorted), 1)
    assert_eq(lp_only.rows_sorted[0].artist_display, "Miles Davis")


def test_sort_imported_rows():
    rows = rows_from_records(
        [
            {"Artist": "The Beatles", "Title": "Abbey Road", "Year": "1969", "Format": "LP"},
            {"Artist": "Miles Davis", "Title": "Kind of Blue", "Year": "1959", "Format": "Vinyl, LP"},
        ]
    )
    sorted_rows = sort_rows(rows, "normal")
    assert_eq(sorted_rows[0].artist_display, "The Beatles")
    assert_eq(sorted_rows[1].artist_display, "Miles Davis")


def main():
    test_parse_discogs_release_id()
    test_format_categories_from_str()
    test_sort_imported_rows()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_csv_round_trip(tmp)
        test_json_round_trip(tmp)
        test_spreadsheet_headers(tmp)
        test_empty_and_bad_files(tmp)
        test_local_store_and_build_once(tmp)
    print("All collection import assertions passed.")


if __name__ == "__main__":
    main()
