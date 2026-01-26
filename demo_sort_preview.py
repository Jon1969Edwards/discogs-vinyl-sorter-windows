"""Demonstrate sorting differences for last-name-first with and without band-safe flag.
Run: python demo_sort_preview.py
Does not hit Discogs API; uses synthetic sample releases.
"""
from pathlib import Path
import sys
sys.path.insert(0, "/Applications/Discogs App")
import discogs_app as app

SAMPLES = [
    ("Box Tops", "Cry Like A Baby", 1968),
    ("Miles Davis", "Kind of Blue", 1959),
    ("The Beatles", "Revolver", 1966),
    ("Beach Boys", "Pet Sounds", 1966),
    ("Thelonious Monk", "Monk's Dream", 1963),
    ("Jean-Michel Jarre", "Oxygene", 1976),
    ("Fine Young Cannibals", "The Raw & The Cooked", 1989),
]


def make_row(artist: str, title: str, year: int, *, lnf: bool, safe_bands: bool):
    sort_artist, sort_title = app.make_sort_keys(
        artist,
        title,
        extra_articles=[],
        last_name_first=lnf,
        lnf_allow_3=False,
        lnf_exclude=set(),
        lnf_safe_bands=safe_bands,
    )
    return {
        "display": artist,
        "title": title,
        "year": year,
        "sort_artist": sort_artist,
        "sort_title": sort_title,
    }


def render(rows):
    # Mimic minimal formatting from write_txt (no label/country)
    return [f"{r['display']} — {r['title']} ({r['year']}) [key:{r['sort_artist']}]" for r in rows]


def scenario(lnf: bool, safe: bool):
    rows = [make_row(a, t, y, lnf=lnf, safe_bands=safe) for a, t, y in SAMPLES]
    # Sort similar to sort_rows (various policy irrelevant here)
    rows_sorted = sorted(rows, key=lambda r: (r['sort_artist'], r['sort_title'], r['year']))
    return render(rows_sorted)


def main():
    print("Scenario A: --last-name-first (without --lnf-safe-bands)\n")
    for line in scenario(lnf=True, safe=False):
        print(line)
    print("\nScenario B: --last-name-first --lnf-safe-bands\n")
    for line in scenario(lnf=True, safe=True):
        print(line)

    print("\nNotes:\n - Expect 'Box Tops' to flip only in Scenario A (tops, box).\n - 'Beach Boys' flips only in Scenario A.\n - Personal names (Miles Davis, Thelonious Monk, Jean-Michel Jarre) flip in both.\n - Three-word band 'Fine Young Cannibals' remains literal in both.\n")

if __name__ == "__main__":
    main()
