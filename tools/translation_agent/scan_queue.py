"""
Translation queue logic — pure functions, no Google Sheets access.

The domain tab of the consolidated scan sheet is a persistent queue. Each scan
reconciles it with what the scan found instead of rewriting it, so rows people
added or edited (row splits, Priority, Status, Comments, manual ISSUE rows)
survive. Rows are dicts keyed by column name (config.HEADERS_QUEUE), so column
order in the sheet doesn't matter.

Scanner-derived issues (MISSING, OUTDATED) are tracked per row by language:
  - a language the scan no longer flags is removed from every row tracking it;
  - a row with no language left is closed (returned for the history tab);
  - flagged languages that no open row tracks get a new row at the bottom.
Other issues (ISSUE) can't be seen by the scan: they are only validated (post
folder exists, languages supported — Status 'invalid' with the reason in Notes
otherwise) and Step 2 closes them when it has retranslated their languages.
Old EXTRA rows are dropped (EXTRA lives in the cleanup tab).

Work order (order_rows): Priority, then first in, first out (sheet order) —
except OUTDATED rows, which go newest post first (folder date).

The sheet I/O around this lives in io_google_spreadsheet.py.
"""

import re
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Tuple

import config

Row = Dict[str, str]

SCANNER_ISSUES = (config.ISSUE_MISSING, config.ISSUE_OUTDATED)

C_DOMAIN  = config.KEY_DOMAIN
C_PRODUCT = config.KEY_PRODUCT_NAME
C_SLUG    = config.KEY_DIR_BASE
C_ISSUE   = config.KEY_ISSUE
C_LANGS   = config.KEY_MISSING_FILES
C_COUNT   = config.KEY_MISSING_COUNT
C_STATUS  = config.KEY_STATUS
C_NOTES   = config.KEY_NOTES


def split_langs(value) -> List[str]:
    """'de, fr,  it' -> ['de', 'fr', 'it'] (order kept, blanks dropped)."""
    return [l.strip() for l in str(value or "").split(",") if l.strip()]


def join_langs(langs: Iterable[str]) -> str:
    return ", ".join(langs)


def days_between(first: str, last: str) -> str:
    """Whole days between two ISO dates/timestamps ('' if either can't be parsed)."""
    try:
        return str((datetime.fromisoformat(str(last)[:10]) - datetime.fromisoformat(str(first)[:10])).days)
    except (ValueError, TypeError):
        return ""


def is_open(row: Row) -> bool:
    """Open rows are worked on by Step 2; invalid / hold / other values are not."""
    return str(row.get(C_STATUS, "")).strip().lower() in config.STATUS_OPEN_VALUES


def row_key(row: Row) -> Tuple[str, str, str, str]:
    return (str(row.get(C_DOMAIN, "")).strip(), str(row.get(C_PRODUCT, "")).strip(),
            str(row.get(C_SLUG, "")).strip(), str(row.get(C_ISSUE, "")).strip())


def is_blank(row: Row) -> bool:
    """Empty rows and old placeholder rows ('!!! NO MISSING TRANSLATION FOUND !!!')."""
    return not str(row.get(C_DOMAIN, "")).strip() or not str(row.get(C_SLUG, "")).strip()


INVALID_PREFIX = "⚠️ Invalid: "


def strip_invalid_note(notes: str) -> str:
    return "\n".join(l for l in str(notes or "").split("\n") if not l.startswith(INVALID_PREFIX)).strip()


def validate_manual_row(row: Row, posts: set, supported_langs: List[str]) -> None:
    """
    Check a row the scan can't see (ISSUE, or an unknown issue) against the repo:
    its post folder must exist (non-draft, with index.md) and its languages must
    be supported. Blank languages mean every supported language. An invalid row
    gets Status 'invalid' and a '⚠️ Invalid: …' line on top of its Notes (the
    person's own note is kept below); once fixed, both are cleared.
    """
    problems = []
    issue = str(row.get(C_ISSUE, "")).strip()
    if issue not in config.ISSUE_ACTIONS or issue == config.ISSUE_EXTRA:
        problems.append(f"unknown issue '{issue}' (use {config.ISSUE_ISSUE})")
    if (str(row.get(C_PRODUCT, "")).strip(), str(row.get(C_SLUG, "")).strip()) not in posts:
        problems.append("post folder not found (or the post is a draft) — check Product / Blog Post Directory")
    langs = split_langs(row.get(C_LANGS))
    if not langs:
        langs = list(supported_langs)
        row[C_LANGS] = join_langs(langs)
    bad = [l for l in langs if l not in supported_langs]
    if bad:
        problems.append(f"unsupported language(s): {join_langs(bad)}")
    row[C_COUNT] = str(len(langs))

    status = str(row.get(C_STATUS, "")).strip().lower()
    notes = strip_invalid_note(row.get(C_NOTES, ""))
    if problems:
        row[C_STATUS] = config.STATUS_INVALID
        row[C_NOTES] = f"{INVALID_PREFIX}{'; '.join(problems)}" + (f"\n{notes}" if notes else "")
    elif status == config.STATUS_INVALID:
        row[C_STATUS] = ""
        row[C_NOTES] = notes


def priority_rank(row: Row) -> int:
    """Rank for ordering (lower first). A blank or unknown Priority falls back to the issue's default."""
    p = str(row.get(config.KEY_PRIORITY, "")).strip().capitalize()
    if p not in config.PRIORITY_RANK:
        p = config.DEFAULT_PRIORITY.get(str(row.get(C_ISSUE, "")).strip(), config.PRIORITY_NORMAL)
    return config.PRIORITY_RANK[p]


_POST_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def post_date(slug) -> int:
    """The post's date from its folder name (`2026-11-18-my-post` → 20261118); 0 when it has none."""
    m = _POST_DATE.match(str(slug).strip())
    return int("".join(m.groups())) if m else 0


def order_rows(rows: list, rank: Callable, is_outdated: Callable, slug: Callable) -> list:
    """
    Work order of queue rows: by `rank` (Priority), sheet order within a rank —
    first in, first out — except OUTDATED rows, which take the OUTDATED places
    of their rank newest post first (folder date; undated folders last, ties
    keep sheet order). MISSING and ISSUE rows never move, and a row whose
    Priority was raised keeps its rank.
    """
    out = sorted(rows, key=rank)                      # stable: sheet order within a rank
    for r in sorted({rank(row) for row in out}):
        places = [i for i, row in enumerate(out) if rank(row) == r and is_outdated(row)]
        newest = sorted((out[i] for i in places), key=lambda row: -post_date(slug(row)))
        for i, row in zip(places, newest):
            out[i] = row
    return out


def new_row(finding: Row, scan_date: str, langs: List[str]) -> Row:
    """A queue row for scan findings no open row tracks yet."""
    issue = finding[C_ISSUE]
    row = {h: "" for h in config.HEADERS_QUEUE}
    row.update({
        config.KEY_SCAN_DATE    : scan_date,
        config.KEY_MISSING_SINCE: scan_date[:10],
        config.KEY_DAYS_MISSING : "0",
        config.KEY_PRIORITY     : config.DEFAULT_PRIORITY.get(issue, config.PRIORITY_NORMAL),
        C_DOMAIN                : finding[C_DOMAIN],
        C_PRODUCT               : finding[C_PRODUCT],
        C_SLUG                  : finding[C_SLUG],
        config.KEY_POST_URL     : finding.get(config.KEY_POST_URL, ""),
        config.KEY_AUTHOR       : finding.get(config.KEY_AUTHOR, ""),
        C_ISSUE                 : issue,
        C_COUNT                 : str(len(langs)),
        C_LANGS                 : join_langs(langs),
        config.KEY_ACTION       : config.ISSUE_ACTIONS.get(issue, ""),
        config.KEY_SOURCE       : config.SOURCE_SCANNER,
        C_NOTES                 : finding.get(C_NOTES, ""),
    })
    return row


def closed_row(row: Row, scan_date: str, langs: List[str] = None, note: str = None) -> Row:
    """A copy of row marked completed, for the history tab."""
    done = dict(row)
    if langs is not None:
        done[C_LANGS] = join_langs(langs)
        done[C_COUNT] = str(len(langs))
    done[C_STATUS] = config.STATUS_COMPLETED
    done[config.KEY_COMPLETED_DATE] = scan_date
    if note:
        done[C_NOTES] = note
    return done


def reconcile(queue: List[Row], findings: List[Row], scan_date: str,
              posts: set = None, supported_langs: List[str] = None) -> Tuple[List[Row], List[Row], List[Row]]:
    """
    Reconcile the queue with a scan.

    queue    — current domain-tab rows (sheet order).
    findings — what the scan flagged, one dict per (post, issue) with the
               flagged languages in Target Translations, in the order new rows
               should be added (MISSING by folder, then OUTDATED newest post first).
               Only MISSING / OUTDATED findings are reconciled.
    posts / supported_langs — every (product, post folder) the scan saw (non-draft,
               with index.md) and the blog's languages; when given, rows the
               scan can't see (ISSUE) are validated against them.
    Returns (new_queue, closed_rows, added_rows); added_rows are also at the
    end of new_queue.
    """
    flagged = {row_key(f): f for f in findings if f.get(C_ISSUE) in SCANNER_ISSUES}
    flagged_langs = {k: split_langs(f[C_LANGS]) for k, f in flagged.items()}
    tracked: Dict[tuple, set] = {}          # languages open rows still track, per key
    out, closed = [], []

    for row in queue:
        if is_blank(row):
            continue
        row = {**{h: "" for h in config.HEADERS_QUEUE}, **row}
        key = row_key(row)
        issue = key[3]
        if issue == config.ISSUE_EXTRA:
            continue        # EXTRA rows live in the cleanup tab now

        if issue in SCANNER_ISSUES and is_open(row):
            hist = split_langs(row[C_LANGS])
            cur = set(flagged_langs.get(key, []))
            remaining = [l for l in hist if l in cur]
            done = [l for l in hist if l not in cur]
            if not remaining:
                closed.append(closed_row(row, scan_date, langs=hist))
                continue
            if done:
                row[C_LANGS] = join_langs(remaining)
                row[C_COUNT] = str(len(remaining))
                row[C_STATUS] = "partial"
            finding = flagged[key]
            row[C_NOTES] = finding.get(C_NOTES, row[C_NOTES])
            for col in (config.KEY_POST_URL, config.KEY_AUTHOR):
                row[col] = finding.get(col, row[col]) or row[col]
            row[config.KEY_SCAN_DATE] = scan_date
            tracked.setdefault(key, set()).update(remaining)
        elif issue in SCANNER_ISSUES:
            # held / invalid scanner rows still count as tracking their languages,
            # so the scan doesn't add duplicates behind a row someone put on hold
            tracked.setdefault(key, set()).update(split_langs(row[C_LANGS]))
        elif posts is not None and (is_open(row) or
                                    str(row.get(C_STATUS, "")).strip().lower() == config.STATUS_INVALID):
            validate_manual_row(row, posts, supported_langs or [])
            row[config.KEY_SCAN_DATE] = scan_date

        if not str(row.get(config.KEY_MISSING_SINCE, "")).strip():
            row[config.KEY_MISSING_SINCE] = scan_date[:10]
        if not str(row.get(config.KEY_PRIORITY, "")).strip():
            row[config.KEY_PRIORITY] = config.DEFAULT_PRIORITY.get(issue, config.PRIORITY_NORMAL)
        if not str(row.get(config.KEY_SOURCE, "")).strip():
            row[config.KEY_SOURCE] = config.SOURCE_MANUAL
        if not str(row.get(config.KEY_ACTION, "")).strip():
            row[config.KEY_ACTION] = config.ISSUE_ACTIONS.get(issue, "")
        row[config.KEY_DAYS_MISSING] = days_between(row[config.KEY_MISSING_SINCE], scan_date)
        out.append(row)

    added = []
    for key, finding in flagged.items():
        untracked = [l for l in flagged_langs[key] if l not in tracked.get(key, set())]
        if untracked:
            added.append(new_row(finding, scan_date, untracked))

    return out + added, closed, added


def to_values(rows: List[Row], header: List[str]) -> List[List[str]]:
    """Dict rows -> sheet value rows in header order."""
    return [[str(r.get(h, "")) for h in header] for r in rows]


def from_values(values: List[List[str]]) -> Tuple[List[str], List[Row]]:
    """Sheet values (header row first) -> (header, dict rows)."""
    if not values:
        return [], []
    header = [str(h).strip() for h in values[0]]
    rows = []
    for raw in values[1:]:
        raw = list(raw) + [""] * (len(header) - len(raw))
        rows.append({h: raw[i] for i, h in enumerate(header) if h})
    return header, rows


def merged_header(existing: List[str], wanted: List[str]) -> List[str]:
    """Keep the sheet's column order (people may have rearranged or added columns); append missing ones."""
    header = [h for h in existing if h]
    return header + [h for h in wanted if h not in header]
