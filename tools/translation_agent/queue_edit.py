"""
Edit a post's open queue row(s) by hand: Priority and/or the languages.

First used 27 Nov 2026: the csv-to-jpg ISSUE row on blog.groupdocs.cloud was
added with `queue_add.py` without --langs, which writes a blank Target
Translations (= every language, filled in only when Step 2 reads the row), so
people could not see its languages in the sheet; both code-block ISSUE rows
were also raised to Urgent at the owner's request.

What it does (dry run unless --apply):
  - finds the open rows (Status blank / pending / partial) of
    <domain> <product>/<post folder>, optionally only one Issue type;
  - --priority sets Priority (Urgent, High, Normal, Low);
  - --langs sets Target Translations and Count; --all-langs writes the blog's
    full language list (config SupportedLangs);
  - before writing, the tab is backed up as a duplicate tab
    ("bak-YYYYMMDD-HHMM-<tab>"); Google Sheets version history is a second net.
Rows are found by key at write time, cells are written RAW.

Run it only when no translation run is in progress for that blog — Step 2
writes comments to and closes rows in the domain tab after each post.

    python tools/translation_agent/queue_edit.py --domain blog.groupdocs.cloud \\
        --post conversion/<post folder> --issue ISSUE --all-langs --priority Urgent          # dry run
    python tools/translation_agent/queue_edit.py ... --apply
"""

import argparse
import sys
from datetime import datetime
from typing import Dict, List, Optional

import config
import io_google_spreadsheet as gs
import scan_queue as q

PRIORITIES = [config.PRIORITY_URGENT, config.PRIORITY_HIGH, config.PRIORITY_NORMAL, config.PRIORITY_LOW]


def blog_langs(domain: str) -> List[str]:
    return [l for l in config.domains_data[domain][config.KEY_SUPPORTED_LANGS].split("|") if l]


def matching_rows(header: List[str], values: List[List[str]], domain: str, product: str, slug: str,
                  issue: Optional[str] = None) -> List[int]:
    """1-based sheet row numbers of the post's open rows (header is row 1)."""
    out = []
    for n, raw in enumerate(values[1:], start=2):
        row = dict(zip(header, raw + [""] * (len(header) - len(raw))))
        if (row.get(config.KEY_DOMAIN) == domain and row.get(config.KEY_PRODUCT_NAME) == product
                and row.get(config.KEY_DIR_BASE) == slug and q.is_open(row)
                and (issue is None or row.get(config.KEY_ISSUE) == issue)):
            out.append(n)
    return out


def planned_cells(priority: Optional[str], langs: Optional[List[str]]) -> Dict[str, str]:
    """Column name -> new value."""
    cells = {}
    if priority:
        cells[config.KEY_PRIORITY] = priority
    if langs is not None:
        cells[config.KEY_MISSING_FILES] = q.join_langs(langs)
        cells[config.KEY_MISSING_COUNT] = str(len(langs))
    return cells


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Edit a post's open queue row(s): Priority and/or languages")
    parser.add_argument("--domain", required=True, choices=sorted(config.domains_data))
    parser.add_argument("--post", required=True, help="<product>/<post folder>")
    parser.add_argument("--issue", choices=[config.ISSUE_MISSING, config.ISSUE_OUTDATED, config.ISSUE_ISSUE],
                        help="only rows of this Issue type")
    parser.add_argument("--priority", choices=PRIORITIES)
    langs = parser.add_mutually_exclusive_group()
    langs.add_argument("--langs", help="comma-separated language codes")
    langs.add_argument("--all-langs", action="store_true", help="the blog's full language list")
    parser.add_argument("--apply", action="store_true", help="make the change (default: dry run)")
    args = parser.parse_args(argv)

    product, _, slug = args.post.strip("/").partition("/")
    new_langs = (blog_langs(args.domain) if args.all_langs
                 else [l.strip() for l in args.langs.split(",") if l.strip()] if args.langs else None)
    cells = planned_cells(args.priority, new_langs)
    if not cells:
        parser.error("nothing to change: give --priority, --langs or --all-langs")

    ws = gs.get_scan_worksheet(args.domain)
    if not ws:
        print("❌ Could not open the domain tab (check GOOGLE_SERVICE_ACCOUNT_JSON / TRANSLATION_SCAN_SHEET_ID).")
        return 1
    values = ws.get_all_values()
    header = [str(h).strip() for h in values[0]] if values else []
    missing = [c for c in cells if c not in header]
    if missing:
        print(f"❌ Column(s) not in the tab: {', '.join(missing)}")
        return 1
    rows = matching_rows(header, values, args.domain, product, slug, args.issue)
    if not rows:
        print(f"❌ No open row for {args.domain} {product}/{slug}" + (f" ({args.issue})" if args.issue else ""))
        return 1

    print(f"{'APPLY' if args.apply else 'DRY RUN'} — {args.domain} {product}/{slug}")
    for n in rows:
        old = values[n - 1]
        for col, new in cells.items():
            i = header.index(col)
            before = old[i] if i < len(old) else ""
            print(f"  row {n} · {col}: {before!r} → {new!r}")
    if not args.apply:
        print("Dry run — nothing written.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    ws.spreadsheet.duplicate_sheet(ws.id, new_sheet_name=f"bak-{stamp}-{ws.title}"[:100])
    # Find the rows again right before writing: Step 2 or a person may have moved them.
    values = ws.get_all_values()
    rows = matching_rows(header, values, args.domain, product, slug, args.issue)
    updates = [{"range": gs.gspread.utils.rowcol_to_a1(n, header.index(col) + 1), "values": [[new]]}
               for n in rows for col, new in cells.items()]
    ws.batch_update(updates, value_input_option="RAW")
    print(f"✅ Updated {len(rows)} row(s); backup tab: bak-{stamp}-{ws.title}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
