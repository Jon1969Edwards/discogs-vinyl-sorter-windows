# Lightweight assertions for TXT divider output. Run: python test_export_dividers.py

from core.export import generate_txt_lines, resolve_divider_mode, sort_letter_to_shelf
from core.models import ReleaseRow


def _row(artist: str, sort_artist: str) -> ReleaseRow:
  return ReleaseRow(
    artist_display=artist,
    title="Album",
    year=2000,
    label="",
    catno="",
    country="",
    format_str="",
    discogs_url="",
    notes="",
    sort_artist=sort_artist,
    sort_title="album",
  )


def assert_eq(a, b, msg: str = ""):
  if a != b:
    raise AssertionError(msg or f"Expected {b!r}, got {a!r}")


def main():
  assert_eq(resolve_divider_mode(False, None), "none")
  assert_eq(resolve_divider_mode(True, None), "letter")
  assert_eq(resolve_divider_mode(False, "abc"), "abc")
  assert_eq(sort_letter_to_shelf("A"), "A")
  assert_eq(sort_letter_to_shelf("H"), "A")
  assert_eq(sort_letter_to_shelf("I"), "B")
  assert_eq(sort_letter_to_shelf("P"), "B")
  assert_eq(sort_letter_to_shelf("Q"), "C")
  assert_eq(sort_letter_to_shelf("#"), "A")

  rows = [
    _row("Arctic Monkeys", "arctic monkeys"),
    _row("Iron Maiden", "iron maiden"),
    _row("Queen", "queen"),
  ]
  lines = generate_txt_lines(rows, divider_mode="abc")
  assert_eq(lines[0], "=== SHELF A (A–H) ===")
  assert "Arctic Monkeys" in lines[1]
  assert_eq(lines[2], "=== SHELF B (I–P) ===")
  assert "Iron Maiden" in lines[3]
  assert_eq(lines[4], "=== SHELF C (Q–Z) ===")
  assert "Queen" in lines[5]

  letter_lines = generate_txt_lines(rows, divider_mode="letter")
  assert_eq(letter_lines[0], "=== A ===")
  assert_eq(letter_lines[2], "=== I ===")
  assert_eq(letter_lines[4], "=== Q ===")

  print("All export divider assertions passed.")


if __name__ == "__main__":
  main()
