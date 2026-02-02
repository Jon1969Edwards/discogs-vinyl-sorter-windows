#!/usr/bin/env python3
"""
Discogs 33⅓ LP Shelf Sorter

Fetches your Discogs collection with a Personal Access Token, filters to
Vinyl LPs at 33⅓ RPM, normalizes artist/title for sorting (e.g., strips
leading articles and Discogs numeric suffixes like "(2)"), and outputs
both a printable shelf order (TXT) and a CSV.

Token discovery order:
- CLI: --token
- Environment: DISCOGS_TOKEN
- Optional .env file (if python-dotenv is installed)

Usage examples:
  python discogs_app.py --user-agent "VinylSorter/1.0 (you@example.com)"
  python discogs_app.py --various-policy last --articles-extra "le,la,les,el,los,las,der,die,das"
"""

from __future__ import annotations

# Version constant
VERSION = "0.2.0"

# Re-export all public APIs for backward compatibility
from core.api import (
    API_BASE,
    get_token,
    discogs_headers,
    api_get,
    get_identity,
    fetch_release_price,
    fetch_prices_for_rows,
    iterate_collection,
)

from core.sorting import (
    strip_discogs_numeric_suffix,
    normalize_apostrophes,
    make_sort_keys,
    is_lp_33,
    is_vinyl_45,
    is_cd_format,
    build_release_row,
    collect_lp_rows,
    collect_45_rows,
    collect_cd_rows,
    sort_rows,
    build_artist_display,
)

from core.export import (
    generate_txt_lines,
    write_txt,
    write_csv,
    write_json,
    rows_to_json,
)

# CLI-specific imports
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Load .env if available
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Discogs LP shelf sorter")
  parser.add_argument(
    "--version",
    action="version",
    version=f"%(prog)s {VERSION}",
    help="Show program's version number and exit.",
  )
  parser.add_argument(
    "--token",
    help="Discogs Personal Access Token. If omitted, reads DISCOGS_TOKEN env var.",
  )
  parser.add_argument(
    "--user-agent",
    default="VinylSorter/1.0 (+contact)",
    help="User-Agent header per Discogs API policy (include a way to contact you).",
  )
  parser.add_argument(
    "--various-policy",
    choices=["normal", "last", "title"],
    default="normal",
    help="How to treat 'Various' artists when sorting: normal sort, push to end, or sort by title (so they file under the release title).",
  )
  parser.add_argument(
    "--articles-extra",
    default="",
    help="Comma-separated extra leading articles to strip for sorting (e.g., 'le,la,les,el,los,las,der,die,das').",
  )
  parser.add_argument(
    "--output-dir",
    default=".",
    help="Directory where outputs are written (vinyl_shelf_order.txt/.csv).",
  )
  parser.add_argument(
    "--dividers",
    action="store_true",
    help="Insert letter dividers (=== A ===) in the TXT output.",
  )
  parser.add_argument(
    "--json",
    action="store_true",
    help="Also write a JSON export (vinyl_shelf_order.json).",
  )
  parser.add_argument(
    "--include-45s",
    action="store_true",
    help="Additionally write outputs for 7\" 45 RPM vinyl singles (files: vinyl45_shelf_order.*).",
  )
  parser.add_argument(
    "--include-cds",
    action="store_true",
    help="Additionally write outputs for CDs (files: cd_shelf_order.*).",
  )
  parser.add_argument(
    "--valuable-sek",
    type=float,
    default=None,
    help="Emit a separate TXT listing items whose Discogs lowest_price is >= this threshold (SEK). Example: --valuable-sek 500",
  )
  parser.add_argument(
    "--last-name-first",
    action="store_true",
    help="Sort artists by last word of their name when heuristic applies (does not change display).",
  )
  parser.add_argument(
    "--lnf-safe-bands",
    action="store_true",
    help="When used with --last-name-first, avoid flipping obvious band-like two-word names (e.g., plural nouns, 'Orchestra', 'Trio').",
  )
  parser.add_argument(
    "--txt-align",
    action="store_true",
    help="Align artist and title columns in TXT output for easier scanning.",
  )
  parser.add_argument(
    "--show-country",
    action="store_true",
    help="Include country code at end of TXT lines if present.",
  )
  parser.add_argument(
    "--max-pages",
    type=int,
    default=None,
    help="Optional safety cap for number of collection pages to fetch.",
  )
  parser.add_argument(
    "--per-page",
    type=int,
    default=100,
    help="Items per page for API pagination (max 100).",
  )
  parser.add_argument(
    "--lp-strict",
    action="store_true",
    help="Require explicit 33 RPM in format descriptions (default: LP implies ~33 even if RPM missing).",
  )
  parser.add_argument(
    "--lp-probable-33",
    action="store_true",
    help="Treat LP/Album as 33 RPM unless descriptors explicitly show 45/78; safer than default but not as strict as --lp-strict.",
  )
  parser.add_argument(
    "--report-filters",
    action="store_true",
    help="When used with --lp-probable-33, write a report of LPs excluded due to explicit 45/78 descriptors.",
  )
  parser.add_argument(
    "--debug-stats",
    action="store_true",
    help="Print summary stats about how many items were filtered out by format checks.",
  )
  return parser.parse_args()


def _normalize_exclude_name(s: str) -> str:
  import re
  return re.sub(r"\s+", " ", (s or "").strip().lower())


def main() -> None:
    args = parse_args()
    token = get_token(args.token)
    headers = discogs_headers(token, args.user_agent)

    print(f"Discogs LP Sorter v{VERSION}")

    ident = get_identity(headers)
    username = ident.get("username")
    if not username:
        sys.exit("Error: Could not determine username from token.")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extra_articles = [a.strip() for a in (args.articles_extra or "").split(",") if a.strip()]

    rows, _ = fetch_and_report_lp_rows(args, headers, username, extra_articles)
    if not rows:
        return

    rows_sorted = sort_rows(rows, args.various_policy)
    write_main_outputs(args, out_dir, rows_sorted)

    rows45_sorted = handle_optional_45s(args, headers, username, extra_articles, out_dir)
    rows_cd_sorted = handle_optional_cds(args, headers, username, extra_articles, out_dir)

    print_category_summary(rows_sorted, rows45_sorted, rows_cd_sorted)

    handle_combined_json(args, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted)
    handle_probable_exclusions(args, out_dir, rows)
    handle_valuable_export(args, out_dir, headers, rows_sorted, rows45_sorted, rows_cd_sorted)

def fetch_and_report_lp_rows(args, headers, username, extra_articles):
    from core.models import ReleaseRow
    dbg: Optional[Dict[str, int]] = {} if args.debug_stats else None
    print(f"Fetching collection for user '{username}'...")
    rows = collect_lp_rows(
        headers=headers,
        username=username,
        per_page=max(1, min(int(args.per_page), 100)),
        max_pages=args.max_pages,
        extra_articles=extra_articles,
        lp_strict=bool(args.lp_strict),
        lp_probable=bool(getattr(args, "lp_probable_33", False)),
        debug_stats=dbg,
        last_name_first=bool(args.last_name_first),
        lnf_allow_3=bool(getattr(args, "lnf_allow_3", False)),
        lnf_exclude={_normalize_exclude_name(s) for s in (getattr(args, "lnf_exclude", "").split(";") if getattr(args, "lnf_exclude", "") else []) if s.strip()},
        lnf_safe_bands=bool(getattr(args, "lnf_safe_bands", False)),
        collect_exclusions=bool(getattr(args, "report_filters", False)),
    )
    if not rows:
        print("No matching 33⅓ RPM LPs found.")
        if args.debug_stats:
            print("Tip: Re-run without strict RPM requirement (default) or enable debug stats with --debug-stats.")
        return [], dbg
    if args.debug_stats and dbg is not None:
        print(
            f"Stats: scanned={dbg.get('scanned', 0)}, vinyl={dbg.get('vinyl', 0)}, "
            f"vinyl+LP={dbg.get('vinyl_lp', 0)}, vinyl+LP+33rpm={dbg.get('vinyl_lp_33', 0)}"
        )
        if getattr(args, "report_filters", False) and getattr(args, "lp_probable_33", False) and not getattr(args, "lp_strict", False):
            excl = getattr(rows, "excluded_probable_basics", [])
            print(f"Probable exclusions (explicit 45/78): {len(excl)}")
    return rows, dbg

def write_main_outputs(args, out_dir, rows_sorted):
    txt_path = out_dir / "vinyl_shelf_order.txt"
    csv_path = out_dir / "vinyl_shelf_order.csv"
    write_txt(rows_sorted, txt_path, dividers=bool(args.dividers), align=bool(args.txt_align), show_country=bool(args.show_country))
    write_csv(rows_sorted, csv_path)
    if args.json:
        json_path = out_dir / "vinyl_shelf_order.json"
        write_json(rows_sorted, json_path)
    print(f"Wrote: {txt_path}")
    print(f"Wrote: {csv_path}")
    if args.json:
        print(f"Wrote: {json_path}")

def handle_optional_45s(args, headers, username, extra_articles, out_dir):
    from core.models import ReleaseRow
    rows45_sorted: List[ReleaseRow] = []
    if getattr(args, "include_45s", False):
        rows45 = collect_45_rows(
            headers=headers,
            username=username,
            per_page=max(1, min(int(args.per_page), 100)),
            max_pages=args.max_pages,
            extra_articles=extra_articles,
            last_name_first=bool(args.last_name_first),
            lnf_allow_3=bool(getattr(args, "lnf_allow_3", False)),
            lnf_exclude={_normalize_exclude_name(s) for s in (getattr(args, "lnf_exclude", "").split(";") if getattr(args, "lnf_exclude", "") else []) if s.strip()},
            lnf_safe_bands=bool(getattr(args, "lnf_safe_bands", False)),
        )
        rows45_sorted = sort_rows(rows45, args.various_policy)
        txt45 = out_dir / "vinyl45_shelf_order.txt"
        csv45 = out_dir / "vinyl45_shelf_order.csv"
        write_txt(rows45_sorted, txt45, dividers=bool(args.dividers), align=bool(args.txt_align), show_country=bool(args.show_country))
        write_csv(rows45_sorted, csv45)
        if args.json:
            json45 = out_dir / "vinyl45_shelf_order.json"
            write_json(rows45_sorted, json45)
        print(f"Wrote: {txt45}")
        print(f"Wrote: {csv45}")
        if args.json:
            print(f"Wrote: {json45}")
    return rows45_sorted

def handle_optional_cds(args, headers, username, extra_articles, out_dir):
    from core.models import ReleaseRow
    rows_cd_sorted: List[ReleaseRow] = []
    if getattr(args, "include_cds", False):
        rows_cd = collect_cd_rows(
            headers=headers,
            username=username,
            per_page=max(1, min(int(args.per_page), 100)),
            max_pages=args.max_pages,
            extra_articles=extra_articles,
            last_name_first=bool(args.last_name_first),
            lnf_allow_3=bool(getattr(args, "lnf_allow_3", False)),
            lnf_exclude={_normalize_exclude_name(s) for s in (getattr(args, "lnf_exclude", "").split(";") if getattr(args, "lnf_exclude", "") else []) if s.strip()},
            lnf_safe_bands=bool(getattr(args, "lnf_safe_bands", False)),
        )
        rows_cd_sorted = sort_rows(rows_cd, args.various_policy)
        txtcd = out_dir / "cd_shelf_order.txt"
        csvcd = out_dir / "cd_shelf_order.csv"
        write_txt(rows_cd_sorted, txtcd, dividers=bool(args.dividers), align=bool(args.txt_align), show_country=bool(args.show_country))
        write_csv(rows_cd_sorted, csvcd)
        if args.json:
            jsoncd = out_dir / "cd_shelf_order.json"
            write_json(rows_cd_sorted, jsoncd)
        print(f"Wrote: {txtcd}")
        print(f"Wrote: {csvcd}")
        if args.json:
            print(f"Wrote: {jsoncd}")
    return rows_cd_sorted

def print_category_summary(rows_sorted, rows45_sorted, rows_cd_sorted):
    summary_parts = [f"LP: {len(rows_sorted)}"]
    if rows45_sorted:
        summary_parts.append(f"45s: {len(rows45_sorted)}")
    if rows_cd_sorted:
        summary_parts.append(f"CDs: {len(rows_cd_sorted)}")
    print("Summary: " + " • ".join(summary_parts))

def handle_combined_json(args, out_dir, rows_sorted, rows45_sorted, rows_cd_sorted):
    if args.json and (rows45_sorted or rows_cd_sorted):
        import json as _json
        combined = []
        for r in rows_sorted:
            combined.append({"media_type": "LP", **rows_to_json([r])[0]})
        for r in rows45_sorted:
            combined.append({"media_type": "45", **rows_to_json([r])[0]})
        for r in rows_cd_sorted:
            combined.append({"media_type": "CD", **rows_to_json([r])[0]})
        combo_path = out_dir / "all_media_shelf_order.json"
        with combo_path.open("w", encoding="utf-8") as f:
            _json.dump(combined, f, ensure_ascii=False, indent=2)
        print(f"Wrote: {combo_path}")

def _write_probable_exclusion_report(excl_basics, out_dir):
    report_path = out_dir / "excluded_probable_lp.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("=== LPs excluded in probable 33 mode (explicit 45/78 descriptors) ===\n")
        for b in excl_basics:
            title = b.get("title") or ""
            artists = build_artist_display(b)
            desc_tokens = []
            for fmt in (b.get("formats") or []):
                if (fmt.get("name") or "").strip().lower() == "vinyl":
                    desc_tokens.extend([d for d in (fmt.get("descriptions") or []) if d])
            line = f"{artists} — {title} | descriptors: {', '.join(desc_tokens)}"
            f.write(line + "\n")
    print(f"Wrote: {report_path}")

def handle_probable_exclusions(args, out_dir, rows):
    should_report = (
        getattr(args, "report_filters", False)
        and getattr(args, "lp_probable_33", False)
        and not getattr(args, "lp_strict", False)
    )
    if not should_report:
        return
    excl_basics = getattr(rows, "excluded_probable_basics", [])
    if excl_basics:
        _write_probable_exclusion_report(excl_basics, out_dir)

def handle_valuable_export(args, out_dir, headers, rows_sorted, rows45_sorted, rows_cd_sorted):
    from core.models import ReleaseRow
    if not getattr(args, "valuable_sek", None):
        return
    threshold = float(args.valuable_sek)
    candidates = _gather_valuable_candidates(rows_sorted, rows45_sorted, rows_cd_sorted)
    print(f"Evaluating prices for {len(candidates)} items (threshold: {threshold:.0f} SEK)…")
    valuable = _find_valuable_items(candidates, headers, threshold)
    _write_valuable_report(valuable, threshold, args, out_dir)

def _gather_valuable_candidates(rows_sorted, rows45_sorted, rows_cd_sorted):
    from core.models import ReleaseRow
    candidates: List[ReleaseRow] = []
    candidates.extend(rows_sorted)
    if rows45_sorted:
        candidates.extend(rows45_sorted)
    if rows_cd_sorted:
        candidates.extend(rows_cd_sorted)
    return candidates

def _lowest_price_sek(rel_id: int, headers) -> Optional[float]:
    url = f"{API_BASE}/releases/{rel_id}"
    resp = api_get(url, headers, params={"curr_abbr": "SEK"})
    try:
        lp = resp.json().get("lowest_price")
        return float(lp) if lp is not None else None
    except Exception:
        return None

def _find_valuable_items(candidates, headers, threshold):
    valuable: List[tuple] = []
    price_cache: Dict[int, Optional[float]] = {}
    for r in candidates:
        rid = r.release_id
        if not isinstance(rid, int):
            continue
        if rid not in price_cache:
            price_cache[rid] = _lowest_price_sek(rid, headers)
        p = price_cache[rid]
        if p is not None and p >= threshold:
            valuable.append((r, p))
    return valuable

def _write_valuable_report(valuable, threshold, args, out_dir):
    if valuable:
        out_path = out_dir / f"valuable_over_{int(threshold)}kr.txt"
        with out_path.open("w", encoding="utf-8") as f:
            f.write(f"=== Valuable items >= {int(threshold)} SEK ===\n")
            for r, p in valuable:
                line = generate_txt_lines([r], dividers=False, align=False, show_country=bool(args.show_country))[0]
                f.write(f"{line} [~{p:.0f} SEK]\n")
        print(f"Wrote: {out_path} ({len(valuable)} items)")
    else:
        print(f"No items found at or above {int(threshold)} SEK.")


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\nInterrupted.")
    sys.exit(130)
  except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
