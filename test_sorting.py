# Lightweight assertions for sorting heuristics. Run with the workspace Python.
# This is intentionally simple (no pytest dependency).

import sys
from typing import Set

sys.path.insert(0, "/Applications/Discogs App")
import discogs_app as app  # noqa: E402
from core.models import ReleaseRow


def assert_eq(a, b, msg: str = ""):
    if a != b:
        raise AssertionError(msg or f"Expected {b!r}, got {a!r}")


def sort_key(artist: str, title: str = "X", *, lnf=False, safe=False, extra=None, exclude: Set[str] = set()):
    extra = extra or []
    k = app.make_sort_keys(
        artist,
        title,
        extra_articles=extra,
        last_name_first=lnf,
        lnf_allow_3=False,
        lnf_exclude=exclude,
        lnf_safe_bands=safe,
    )
    return k[0]


def main():
    # 1) Band-safe behavior: Box Tops should not flip when safe-bands is ON
    safe_key = sort_key("Box Tops", lnf=True, safe=True)
    assert_eq(safe_key, "box tops", "Band-safe: 'Box Tops' should remain literal under safe-bands")

    # 2) Default LNF: Box Tops flips without safe-bands
    default_key = sort_key("Box Tops", lnf=True, safe=False)
    assert_eq(default_key, "tops, box", "Default LNF: 'Box Tops' should flip without safe-bands")

    # 3) Person: Miles Davis flips either way
    md_default = sort_key("Miles Davis", lnf=True, safe=False)
    assert_eq(md_default, "davis, miles", "Miles Davis should flip by default")
    md_safe = sort_key("Miles Davis", lnf=True, safe=True)
    assert_eq(md_safe, "davis, miles", "Miles Davis should also flip with safe-bands on")

    # 4) Article stripping: The Beatles -> beatles (no flip unless lnf+safe rules allow, but plural should prevent flip)
    beatles_default = sort_key("The Beatles", lnf=True, safe=False, extra=["the"])  # extra not necessary; 'the' is default
    assert_eq(beatles_default, "beatles", "Article stripping should remove 'The'")
    beatles_safe = sort_key("The Beatles", lnf=True, safe=True)
    assert_eq(beatles_safe, "beatles", "Plural band should remain literal under safe-bands")
    # 5) Person with distinctive first name: Thelonious Monk flips
    monk = sort_key("Thelonious Monk", lnf=True)
    assert_eq(monk, "monk, thelonious", "Thelonious Monk should flip under LNF")

    # 6) Hyphenated given name: Jean-Michel Jarre flips (hyphen preserved)
    jm = sort_key("Jean-Michel Jarre", lnf=True)
    assert_eq(jm, "jarre, jean-michel", "Hyphenated given names should flip correctly")

    # 7) Three-word with particle allowed: Ludwig van Beethoven flips with --lnf-allow-3 semantics
    # Simulate by calling underlying key with allow_3=True via helper access
    k = app.make_sort_keys("Ludwig van Beethoven", "X", extra_articles=[], last_name_first=True, lnf_allow_3=True, lnf_exclude=set(), lnf_safe_bands=True)
    assert_eq(k[0], "beethoven, ludwig van", "Particle 'van' should keep with first name when flipping 3-word names")

    # 8) Plural two-word band: Beach Boys flips by default LNF, but not with safe-bands
    beach_default = sort_key("Beach Boys", lnf=True, safe=False)
    assert_eq(beach_default, "boys, beach", "Default LNF should flip 'Beach Boys'")
    beach_safe = sort_key("Beach Boys", lnf=True, safe=True)
    assert_eq(beach_safe, "beach boys", "Band-safe should keep 'Beach Boys' literal")

    # 9) Multi-word band (no flip even without safe-bands because >2 tokens and not allow_3): Fine Young Cannibals
    fyc = sort_key("Fine Young Cannibals", lnf=True, safe=False)
    assert_eq(fyc, "fine young cannibals", "Three-word band should remain literal with default allow_3=False")

    # 9b) Adjective+noun band: Big Star should NOT flip under safe-bands
    big_star_safe = sort_key("Big Star", lnf=True, safe=True)
    assert_eq(big_star_safe, "big star", "Band-safe: 'Big Star' should remain literal under safe-bands")

    # 10) Various Artists policy: when policy is 'title', a Various item should sort by title
        r1 = ReleaseRow(artist_display="Various Artists", title="Zebra Songs", year=2000, label="", catno="", country="", format_str="", discogs_url="", notes="", release_id=None)
    r1.sort_artist, r1.sort_title = app.make_sort_keys(r1.artist_display, r1.title, extra_articles=[], last_name_first=True, lnf_allow_3=False, lnf_exclude=set(), lnf_safe_bands=True)
        r2 = ReleaseRow(artist_display="Various Artists", title="Alpha Tunes", year=1999, label="", catno="", country="", format_str="", discogs_url="", notes="", release_id=None)
    r2.sort_artist, r2.sort_title = app.make_sort_keys(r2.artist_display, r2.title, extra_articles=[], last_name_first=True, lnf_allow_3=False, lnf_exclude=set(), lnf_safe_bands=True)
    sorted_title = app.sort_rows([r1, r2], "title")
    assert_eq(sorted_title[0].title, "Alpha Tunes", "Various Artists should be filed/sorted by title when various-policy is 'title'")

    print("All sorting assertions passed.")


if __name__ == "__main__":
    main()
