"""
One-time reset of the consolidated scan sheet for the persistent queue
(decided 18 Nov 2026). Run it by hand, only after the translation runs in
progress have finished and committed — never from a workflow.

What it does (dry run unless --apply):
  1. Backs up every tab it changes as a duplicate tab in the same spreadsheet
     ("bak-YYYYMMDD-<tab>"); Google Sheets version history is a second safety net.
  2. History: deletes every row that isn't completed (pending / partial — their
     Missing Since and comments are not kept, by decision) and every row of the
     domains in config.NO_HISTORY_DOMAINS (blog.groupdocs.com), completed or not.
  3. Clears every domain tab down to the queue header row, and the cleanup tab
     down to its header row.

The next scan then rebuilds the queue (a scan against an empty queue is a
rebuild): MISSING (High), then OUTDATED (Low), Missing Since = that day.

    python tools/translation_agent/reset_scan_queue.py            # show what would change
    python tools/translation_agent/reset_scan_queue.py --apply    # do it
"""

import argparse
import sys
from datetime import datetime
from typing import List, Tuple

import gspread

import config
import io_google_spreadsheet as gs

DOMAINS = [
    config.DOMAIN_ASPOSE_COM, config.DOMAIN_GROUPDOCS_COM, config.DOMAIN_CONHOLDATE_COM,
    config.DOMAIN_ASPOSE_CLOUD, config.DOMAIN_GROUPDOCS_CLOUD, config.DOMAIN_CONHOLDATE_CLOUD,
]


def history_rows_to_delete(values: List[list]) -> List[int]:
    """1-based sheet rows of the history tab to delete: not completed, or a no-history domain."""
    if not values:
        return []
    header = [str(h).strip() for h in values[0]]
    c_status, c_domain = header.index("Status"), header.index("Domain")
    rows = []
    for i, row in enumerate(values[1:], start=2):
        row = list(row) + [""] * (len(header) - len(row))
        if not any(str(v).strip() for v in row):
            continue
        if (str(row[c_status]).strip().lower() != config.STATUS_COMPLETED
                or str(row[c_domain]).strip() in config.NO_HISTORY_DOMAINS):
            rows.append(i)
    return rows


def contiguous_ranges(rows: List[int]) -> List[Tuple[int, int]]:
    """[2, 3, 4, 7, 9, 10] -> [(9, 10), (7, 7), (2, 4)] — bottom-up, so deleting one doesn't shift the next."""
    ranges = []
    for r in sorted(rows):
        if ranges and r == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], r)
        else:
            ranges.append((r, r))
    return ranges[::-1]


def delete_rows_requests(sheet_id: int, rows: List[int]) -> List[dict]:
    return [{"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS",
                                           "startIndex": start - 1, "endIndex": end}}}
            for start, end in contiguous_ranges(rows)]


def clear_to_header(ws, header: List[str]) -> None:
    ws.clear()
    ws.update([header], "A1", value_input_option="RAW")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One-time reset of the translation queue sheet")
    parser.add_argument("--apply", action="store_true", help="Make the changes (default: dry run)")
    args = parser.parse_args(argv)

    sh = gs._open_scan_sheet()
    if not sh:
        print("❌ Could not open the consolidated scan sheet (check GOOGLE_SERVICE_ACCOUNT_JSON / TRANSLATION_SCAN_SHEET_ID).")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    tabs = {ws.title: ws for ws in sh.worksheets()}
    plan = []      # (title, description)

    hist = tabs.get(config.HISTORY_TAB)
    hist_delete = history_rows_to_delete(hist.get_all_values()) if hist else []
    if hist:
        plan.append((config.HISTORY_TAB, f"delete {len(hist_delete)} row(s) (pending / partial / "
                                         f"{', '.join(sorted(config.NO_HISTORY_DOMAINS))})"))
    domain_tabs = [tabs[d] for d in DOMAINS if d in tabs]
    for ws in domain_tabs:
        plan.append((ws.title, f"clear {max(len(ws.get_all_values()) - 1, 0)} row(s) → queue header only"))
    cleanup = tabs.get(config.CLEANUP_TAB)
    if cleanup:
        plan.append((cleanup.title, "clear → header only"))

    print(f"{'APPLY' if args.apply else 'DRY RUN'} — consolidated scan sheet")
    for title, what in plan:
        print(f"  {title:<24} {what}")
    if not args.apply:
        print("\nNothing changed. Re-run with --apply to make these changes.")
        return 0

    for title, _ in plan:
        sh.duplicate_sheet(tabs[title].id, new_sheet_name=f"bak-{stamp}-{title}"[:100])
    print(f"✅ Backed up {len(plan)} tab(s) as bak-{stamp}-<tab>.")

    if hist and hist_delete:
        sh.batch_update({"requests": delete_rows_requests(hist.id, hist_delete)})
        gs._ensure_history_columns(hist)
        print(f"✅ History: deleted {len(hist_delete)} row(s).")
    for ws in domain_tabs:
        clear_to_header(ws, config.HEADERS_QUEUE)
    if cleanup:
        clear_to_header(cleanup, config.HEADERS_CLEANUP)
    print(f"✅ Cleared {len(domain_tabs)} domain tab(s){' and the cleanup tab' if cleanup else ''}.")
    print("\nNext: run the scan (workflow 'Scan Missing Translations', manual run) to rebuild the queue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
