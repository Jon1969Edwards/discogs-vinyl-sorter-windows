# Lightweight assertions for format detection and filtering. No pytest dependency.
# Run: python test_format_filter.py

from core.format_filter import filter_rows_by_format
from core.models import ReleaseRow
from core.sorting import detect_format_categories


def assert_eq(a, b, msg: str = ""):
  if a != b:
    raise AssertionError(msg or f"Expected {b!r}, got {a!r}")


def _row(categories):
  return ReleaseRow(
    artist_display="A",
    title="T",
    year=2000,
    label="",
    catno="",
    country="",
    format_str="",
    discogs_url="",
    notes="",
    format_categories=frozenset(categories),
  )


def test_detect_format_categories():
  lp = {
    "formats": [{"name": "Vinyl", "descriptions": ["LP", "Album", "33 \u2153 RPM"]}],
  }
  cats = detect_format_categories(lp)
  assert "lp" in cats and "vinyl" in cats, "Vinyl LP should tag lp and vinyl"

  cd = {"formats": [{"name": "CD", "descriptions": ["Album"]}]}
  assert_eq(sorted(detect_format_categories(cd)), ["cd"])

  box45 = {
    "formats": [
      {"name": "Box Set"},
      {"name": "Vinyl", "descriptions": ["7\"", "45 RPM", "Single"]},
    ],
  }
  cats = detect_format_categories(box45)
  assert "boxset" in cats and "vinyl45" in cats and "vinyl" in cats

  cass = {"formats": [{"name": "Cassette", "descriptions": ["Album"]}]}
  assert_eq(sorted(detect_format_categories(cass)), ["cassette"])


def test_filter_rows_by_format():
  rows = [
    _row({"lp", "vinyl"}),
    _row({"cd"}),
    _row({"vinyl45", "vinyl"}),
  ]

  assert_eq(len(filter_rows_by_format(rows, set())), 3, "empty selection shows all")
  assert_eq(len(filter_rows_by_format(rows, {"everything"})), 3)

  lp_only = filter_rows_by_format(rows, {"lp"})
  assert_eq(len(lp_only), 1)
  assert "lp" in lp_only[0].format_categories

  union = filter_rows_by_format(rows, {"lp", "cd"})
  assert_eq(len(union), 2)

  none = filter_rows_by_format(rows, {"cassette"})
  assert_eq(len(none), 0)


def main():
  test_detect_format_categories()
  test_filter_rows_by_format()
  print("All format filter assertions passed.")


if __name__ == "__main__":
  main()
