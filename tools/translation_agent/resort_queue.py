"""
Re-sort the OUTDATED rows of the queue (domain tabs) newest post first — by
hand, when the sheet should read in the order Step 2 works it. First used
19 Nov 2026, when the work order changed to "OUTDATED newest post first"
(scan_queue.order_rows()) and the rebuilt queue still listed 2022 posts first.

Step 2 sorts the queue itself, so this is only for people reading the sheet;
nothing breaks if it is never run.

What it does (dry run unless --apply):
  - OUTDATED rows swap among the places OUTDATED rows hold, newest post first
    (folder date; undated last; same date keeps sheet order). Every other row
    (MISSING, ISSUE, held, invalid) stays exactly where it is; no cell changes.
  - Before writing, each tab it changes is backed up as a duplicate tab
    ("bak-YYYYMMDD-HHMM-<tab>"); Google Sheets version history is a second net.

Run it only when no translation run is in progress — Step 2 writes comments to
and closes rows in the domain tab after each post.

    python tools/translation_agent/resort_queue.py                     # show what would change
    python tools/translation_agent/resort_queue.py --apply             # do it, all domains
    python tools/translation_agent/resort_queue.py --domain blog.aspose.com --apply
"""

import argparse
import sys
from datetime import datetime
from typing import List, Tuple

import config
import io_google_spreadsheet as gs
import scan_queue as q


def outdated_newest_first(rows: List[dict]) -> Tuple[List[dict], int]:
    """(re-sorted rows, number of rows that moved) — only OUTDATED rows move, among their own places."""
    out = q.order_rows(rows, rank=lambda r: 0,
                       is_outdated=lambda r: str(r.get(config.KEY_ISSUE, "")).strip() == config.ISSUE_OUTDATED,
                       slug=lambda r: r.get(config.KEY_DIR_BASE, ""))
    return out, sum(a is not b for a, b in zip(rows, out))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-sort OUTDATED queue rows newest post first")
    parser.add_argument("--apply", action="store_true", help="Make the changes (default: dry run)")
    parser.add_argument("--domain", choices=sorted(config.domains_data), help="One domain tab (default: all)")
    args = parser.parse_args(argv)

    sh = gs._open_scan_sheet()
    if not sh:
        print("❌ Could not open the consolidated scan sheet (check GOOGLE_SERVICE_ACCOUNT_JSON / TRANSLATION_SCAN_SHEET_ID).")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    tabs = {ws.title: ws for ws in sh.worksheets()}
    domains = [args.domain] if args.domain else list(config.domains_data)

    print(f"{'APPLY' if args.apply else 'DRY RUN'} — OUTDATED rows newest post first")
    changed = 0
    for domain in domains:
        ws = tabs.get(domain)
        if ws is None:
            print(f"  {domain:<24} no tab — skipped")
            continue
        values = ws.get_all_values()
        header, rows = q.from_values(values)
        new_rows, moved = outdated_newest_first(rows)
        outdated = [r for r in new_rows if r.get(config.KEY_ISSUE) == config.ISSUE_OUTDATED]
        first = ", ".join(r.get(config.KEY_DIR_BASE, "")[:40] for r in outdated[:2])
        print(f"  {domain:<24} {len(rows)} row(s), {len(outdated)} OUTDATED, {moved} move"
              + (f" — first: {first}" if moved else ""))
        if args.apply and moved:
            sh.duplicate_sheet(ws.id, new_sheet_name=f"bak-{stamp}-{domain}"[:100])
            gs._write_tab(ws, header, new_rows, values)
            changed += 1

    if not args.apply:
        print("\nNothing changed. Re-run with --apply to make these changes.")
    else:
        print(f"\n✅ Re-sorted {changed} tab(s)" + (f"; backups: bak-{stamp}-<tab>." if changed else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
