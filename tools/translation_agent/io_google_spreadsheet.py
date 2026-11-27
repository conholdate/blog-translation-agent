import os
import json
import gspread
import sys
import config
import scan_queue as queue
from scan_helpers import issue_note
from run_log import detail
from datetime import datetime
from typing import Dict, List, Union # For type hints and better readability
from gspread_formatting import cellFormat, textFormat, format_cell_range # Explicitly import necessary functions/classes

# --- Global Configuration (remains here as it's typically environment-specific) ---
# Path to your Google service account JSON key file.
# Make sure this file is secure and its path is correct.    
# 1. Try to load JSON content from the environment variable
json_content = os.getenv("GOOGLE_CREDENTIALS_JSON_SK")
BASE_DIR = os.getenv("GITHUB_WORKSPACE", os.getcwd())

printing_allowed = False

# History tab constants
# The history tab holds completed rows only (closed queue rows move there);
# 'Scan Date' is when the row was first flagged. Columns are found by name.
HISTORY_TAB             = config.HISTORY_TAB
HISTORY_HEADERS         = [
    "Scan Date", "Domain", "Product", "Blog Post Directory",
    "Blog Post URL", "Author", "Issue", "Target Translations", "Count",
    "Status", "Completed Date", "Comments", "Notes", "Priority", "Source",
]
HISTORY_COMMENT_MAX_LEN  = 45000    # Sheets cell limit is 50,000 chars
HISTORY_STATUS_COMPLETED = config.STATUS_COMPLETED

# ======================================================================================
# Write Function
# ======================================================================================
def get_gc():
    # print("In GET GC....")
    # print(f"✅ GOOGLE_CREDENTIALS_JSON_SK: {json_content}")
    if json_content:
        # This path runs in GitHub Actions (loads from environment secret)
        try:
            credentials_info = json.loads(json_content)
            gc = gspread.service_account_from_dict(credentials_info)
            detail("✅ GSheets client initialized.")
            
            return gc
        
        except json.JSONDecodeError:
            print("❌ Error decoding JSON credentials from environment variable.", file=sys.stderr)

    else:
        # This path runs locally (falls back to file path)

        JSON_KEY_FILE = os.path.join(BASE_DIR, "utils/gsheetapi-missing-translations-sk.json")
        # JSON_KEY_FILE = 'utils/gsheetapi-missing-translations-965225ba12e8.json'

        try:
            # Note: gspread.service_account() is an alias for service_account_from_file()
            # 1. Authenticate with the Google Sheets API.
            gc = gspread.service_account(filename=JSON_KEY_FILE)
            print_on_console("✅ GSheets client initialized using local file.")
            
            return gc
        
        except FileNotFoundError:
            print(f"❌ Error: Credentials file not found at {JSON_KEY_FILE}", file=sys.stderr)
    
    return None

def get_scan_gc():
    """Return a gspread client using GOOGLE_SERVICE_ACCOUNT_JSON (consolidated scan sheet account)."""
    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON
    if not raw:
        print("❌ GOOGLE_SERVICE_ACCOUNT_JSON is not set.", file=sys.stderr)
        return None
    try:
        return gspread.service_account_from_dict(json.loads(raw))
    except (json.JSONDecodeError, Exception) as e:
        print(f"❌ Failed to initialise scan GSheets client: {e}", file=sys.stderr)
        return None


def get_scan_worksheet(domain: str) -> gspread.Worksheet:
    """
    Open the consolidated scan sheet and return the worksheet for the given domain.
    The worksheet title is expected to match the domain name exactly (e.g. 'blog.aspose.com').
    Returns None if the sheet or worksheet cannot be opened.
    """
    gc = get_scan_gc()
    if not gc:
        return None
    try:
        sh = gc.open_by_key(config.TRANSLATION_SCAN_SHEET_ID)
        return sh.worksheet(domain)
    except gspread.exceptions.WorksheetNotFound:
        print(f"❌ Worksheet '{domain}' not found in consolidated scan sheet.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Could not open scan sheet: {e}", file=sys.stderr)
        return None


def _auto_resize_columns(ws: gspread.Worksheet) -> None:
    ws.spreadsheet.batch_update({"requests": [{"autoResizeDimensions": {"dimensions": {
        "sheetId": ws.id, "dimension": "COLUMNS",
        "startIndex": 0, "endIndex": ws.col_count,
    }}}]})


# ======================================================================================
# Translation queue (domain tabs), cleanup tab and history tab
# ======================================================================================
# The domain tab is a persistent queue that each scan reconciles (scan_queue.py)
# instead of rewriting; closed rows move to the history tab, which holds
# completed rows only. Every write re-reads the tab first and finds rows by key
# (domain, product, post folder, issue) — never by a row number remembered from
# earlier — because people and other runs may have edited the tab meanwhile.
# Values are written RAW: comments start with "- " and must never become formulas
# (so the queue tab shouldn't hold formulas either — they'd be kept as values).

def _open_scan_sheet():
    gc = get_scan_gc()
    if not gc:
        return None
    try:
        return gc.open_by_key(config.TRANSLATION_SCAN_SHEET_ID)
    except Exception as e:
        print(f"❌ Could not open scan sheet: {e}", file=sys.stderr)
        return None


def _get_or_create_tab(title: str, header: List[str], rows: int = 1000):
    sh = _open_scan_sheet()
    if not sh:
        return None
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=rows, cols=len(header))
        ws.update([header], "A1", value_input_option="RAW")
        print(f"✅ Created '{title}' worksheet.")
        return ws


def get_scan_tab_url(ws: gspread.Worksheet) -> str:
    """Link straight to a tab of the consolidated scan sheet."""
    try:
        return f"{ws.spreadsheet.url}#gid={ws.id}"
    except Exception:
        return ""


def _write_tab(ws: gspread.Worksheet, header: List[str], rows: List[dict], old_values: List[list]) -> None:
    """
    Overwrite ws from A1 with header + rows, then blank the rows left below.
    The new values are written before anything is cleared, so a failed write
    never leaves the tab empty.
    """
    values = [header] + queue.to_values(rows, header)
    old_n = len(old_values)
    old_w = max((len(r) for r in old_values), default=0)
    width = max(len(header), old_w)
    if ws.row_count < len(values) or ws.col_count < width:
        ws.resize(rows=max(ws.row_count, len(values)), cols=max(ws.col_count, width))
    ws.update(values, "A1", value_input_option="RAW")
    if old_n > len(values):
        ws.batch_clear([f"A{len(values) + 1}:{gspread.utils.rowcol_to_a1(old_n, width)}"])


def sync_domain_queue(domain: str, findings: List[dict], scan_date: str,
                      posts: set = None, supported_langs: List[str] = None) -> dict:
    """
    Reconcile the domain tab (the queue) with this scan's MISSING / OUTDATED
    findings and move closed rows to the history tab (dropped instead for
    config.NO_HISTORY_DOMAINS). posts / supported_langs validate manual rows
    (see scan_queue.validate_manual_row).

    Returns {"ok", "open", "new", "closed", "url"}; ok is False if the queue
    couldn't be read or written (the scan run then reports it, nothing is lost).
    """
    result = {"ok": False, "open": 0, "new": 0, "closed": 0, "url": ""}
    ws = get_scan_worksheet(domain)
    if not ws:
        return result
    try:
        values = ws.get_all_values()
        header, rows = queue.from_values(values)
        new_queue, closed, added = queue.reconcile(rows, findings, scan_date, posts, supported_langs)
        header = queue.merged_header(header, config.HEADERS_QUEUE)
        _write_tab(ws, header, new_queue, values)
        _auto_resize_columns(ws)
        result.update(ok=True, open=len(new_queue), new=len(added), closed=len(closed),
                      url=get_scan_tab_url(ws))
        print(f"✅ Queue '{domain}': {len(new_queue)} open row(s), {result['new']} new, {len(closed)} closed.")
    except Exception as e:
        print(f"❌ Failed to update the '{domain}' queue: {e}", file=sys.stderr)
        return result

    if closed:
        append_history_rows(domain, closed)
    return result


def append_history_rows(domain: str, rows: List[dict]) -> bool:
    """
    Append closed queue rows to the history tab (completed rows only). History's
    'Scan Date' is when the row was first flagged (its Missing Since).
    Rows of config.NO_HISTORY_DOMAINS are dropped. Never raises.
    """
    if not rows:
        return True
    if domain in config.NO_HISTORY_DOMAINS:
        print(f"ℹ️  {len(rows)} closed row(s) of {domain} dropped (no history kept for this domain).")
        return True
    try:
        ws = _get_history_worksheet()
        if not ws:
            return False
        header = ws.row_values(1)

        def value(row, h):
            if h == "Scan Date":
                return str(row.get(config.KEY_MISSING_SINCE) or row.get(config.KEY_SCAN_DATE, ""))
            return str(row.get(h, ""))

        ws.append_rows([[value(r, h) for h in header] for r in rows], value_input_option="RAW")
        print(f"✅ History: {len(rows)} completed row(s) added for '{domain}'.")
        return True
    except Exception as e:
        print(f"❌ Failed to add completed rows to history for '{domain}': {e}", file=sys.stderr)
        return False


def replace_cleanup_rows(domain: str, extra_rows: List[dict], scan_date: str) -> bool:
    """
    Replace this domain's rows in the cleanup tab (EXTRA / junk files of every
    domain) with this scan's. Other domains' rows are kept. Never raises.
    """
    try:
        ws = _get_or_create_tab(config.CLEANUP_TAB, config.HEADERS_CLEANUP)
        if not ws:
            return False
        values = ws.get_all_values()
        header, rows = queue.from_values(values)
        header = queue.merged_header(header, config.HEADERS_CLEANUP)
        keep = [r for r in rows if not queue.is_blank(r) and r.get(config.KEY_DOMAIN) != domain]
        new = [{**r, config.KEY_SCAN_DATE: scan_date} for r in extra_rows]
        _write_tab(ws, header, keep + new, values)
        print(f"✅ Cleanup tab: {len(new)} EXTRA row(s) for '{domain}'.")
        return True
    except Exception as e:
        print(f"❌ Failed to update the cleanup tab for '{domain}': {e}", file=sys.stderr)
        return False


def _rows_in_step2_order(rows: List[dict], columns: List[str]) -> List[list]:
    return [[str(r.get(h, "")) for h in columns] for r in rows if not queue.is_blank(r)]


# What Step 2 gets per row: the classic columns (by index, see translator.py)
# + Priority (col 10) + Ready After (col 11, the settling time)
QUEUE_READ_COLUMNS = config.HEADERS_MISSING_TRANSLATIONS + [config.KEY_PRIORITY, config.KEY_READY_AFTER]


def read_domain_scan_rows(domain: str):
    """
    Read the queue (domain tab) for Step 2.

    Columns are located by name and returned in QUEUE_READ_COLUMNS order
    (HEADERS_MISSING_TRANSLATIONS + Priority + Ready After), so the sheet's own
    column order and extra columns don't matter. Priority / Ready After are ''
    on tabs that don't have them yet (Step 2 then falls back to the issue's
    default priority / treats the row as ready). Rows are kept
    in sheet order; blank and placeholder rows are skipped.

    Returns (rows, scan_date), or (None, "") if the tab can't be read.
    """
    try:
        ws = get_scan_worksheet(domain)
        if not ws:
            return None, ""
        header, rows = queue.from_values(ws.get_all_values())
        if not header:
            return [], ""
        missing = [h for h in config.HEADERS_MISSING_TRANSLATIONS if h not in header]
        if missing:
            print(f"❌ '{domain}' tab is missing column(s) {missing}.", file=sys.stderr)
            return None, ""
        scan_date = next((r.get(config.KEY_SCAN_DATE, "") for r in rows
                          if not queue.is_blank(r) and r.get(config.KEY_SCAN_DATE)), "")
        return _rows_in_step2_order(rows, QUEUE_READ_COLUMNS), scan_date
    except Exception as e:
        print(f"❌ Could not read '{domain}' tab from the consolidated scan sheet: {e}", file=sys.stderr)
        return None, ""


def read_cleanup_rows(domain: str) -> List[list]:
    """This domain's EXTRA rows from the cleanup tab, in HEADERS_MISSING_TRANSLATIONS order ([] if none)."""
    try:
        sh = _open_scan_sheet()
        if not sh:
            return []
        try:
            ws = sh.worksheet(config.CLEANUP_TAB)
        except gspread.exceptions.WorksheetNotFound:
            return []
        header, rows = queue.from_values(ws.get_all_values())
        return _rows_in_step2_order([r for r in rows if r.get(config.KEY_DOMAIN) == domain],
                                    config.HEADERS_MISSING_TRANSLATIONS)
    except Exception as e:
        print(f"⚠️  Could not read the cleanup tab: {e}", file=sys.stderr)
        return []


def append_queue_comment(domain: str, slug: str, comment: str, run_langs: List[str] = None) -> bool:
    """Append the same whole-post comment (e.g. an error or draft skip) to the post's open queue rows."""
    return append_queue_comments(domain, slug, lambda row_langs: comment, run_langs=run_langs)


def append_queue_comments(domain: str, slug: str, comment_for, run_langs: List[str] = None,
                          done_langs: List[str] = None) -> bool:
    """
    Record a Step 2 post result on the post's open queue rows (domain, post
    folder — any issue: MISSING / OUTDATED / ISSUE, or split by hand).

    Comments — comment_for(row_langs) builds the comment for one row:
      - run_langs given: every open row sharing a language with run_langs gets
        comment_for(<those shared languages, in row order>); if no row shares
        one, the last open row gets comment_for(None) (whole-run comment).
      - run_langs None: every open row gets comment_for(None).
      Earlier comments are kept above, separated by a blank line.

    Closing — done_langs (translated, or already there) are removed from every
    open row of the post that tracks them, so one retranslation settles e.g.
    both an OUTDATED and an ISSUE row. A row left with no language is closed:
    removed from the queue and appended to history as completed (dropped for
    config.NO_HISTORY_DOMAINS), its new comment included. Others become 'partial'.

    The tab is re-read here and rows are found by key, so rows added, removed
    or re-sorted since the run started don't matter. Returns True if anything
    was written. Never raises — result logging must not halt the pipeline.
    """
    try:
        ws = get_scan_worksheet(domain)
        if not ws:
            return False

        values = ws.get_all_values()
        header = [str(h).strip() for h in values[0]] if values else []
        if config.KEY_COMMENTS not in header:
            ws.update([[config.KEY_COMMENTS]], gspread.utils.rowcol_to_a1(1, len(header) + 1),
                      value_input_option="RAW")
            header.append(config.KEY_COMMENTS)
        col = {h: header.index(h) + 1 for h in header if h}
        _, rows = queue.from_values([header] + values[1:])

        open_rows = []      # (sheet_row, row dict, row_langs)
        for i, row in enumerate(rows, start=2):
            if (row.get(config.KEY_DOMAIN) == domain and row.get(config.KEY_DIR_BASE) == slug
                    and queue.is_open(row)):
                open_rows.append((i, row, queue.split_langs(row.get(config.KEY_MISSING_FILES))))

        if not open_rows:
            print(f"⚠️  No open queue row for {domain}/{slug}; result not logged.")
            return False

        comments = {}       # sheet_row -> comment
        if run_langs is None:
            comments = {r: comment_for(None) for r, _, _ in open_rows}
        else:
            run = set(run_langs)
            for r, _, langs in open_rows:
                shared = [l for l in langs if l in run]
                if shared:
                    comments[r] = comment_for(shared)
            if not comments:    # no row tracks these languages: keep the comment on the last open row
                comments[open_rows[-1][0]] = comment_for(None)

        done = set(done_langs or [])
        updates, closed, closed_rows = [], [], []

        def cell(r, h, v):
            updates.append({"range": gspread.utils.rowcol_to_a1(r, col[h]), "values": [[v]]})

        for r, row, langs in open_rows:
            text = row.get(config.KEY_COMMENTS, "")
            if r in comments:
                text = f"{text}\n\n{comments[r]}" if text else comments[r]
                if len(text) > HISTORY_COMMENT_MAX_LEN:
                    text = text[-HISTORY_COMMENT_MAX_LEN:]    # drop the oldest lines first
            remaining = [l for l in langs if l not in done]
            if langs and not remaining:
                closed.append(r)
                closed_rows.append(queue.closed_row({**row, config.KEY_COMMENTS: text},
                                                    datetime.now().astimezone().isoformat(), langs=langs))
                continue
            if r in comments:
                cell(r, config.KEY_COMMENTS, text)
            if len(remaining) < len(langs):
                cell(r, config.KEY_MISSING_FILES, queue.join_langs(remaining))
                if config.KEY_MISSING_COUNT in col:
                    cell(r, config.KEY_MISSING_COUNT, str(len(remaining)))
                if config.KEY_STATUS in col:
                    cell(r, config.KEY_STATUS, "partial")

        if updates:
            ws.batch_update(updates, value_input_option="RAW")
        if closed:
            append_history_rows(domain, closed_rows)
            ws.spreadsheet.batch_update({"requests": [
                {"deleteDimension": {"range": {"sheetId": ws.id, "dimension": "ROWS",
                                               "startIndex": r - 1, "endIndex": r}}}
                for r in sorted(closed, reverse=True)]})      # bottom-up: no index shifts
        print(f"✅ Queue updated for {slug}: {len(comments)} comment(s)"
              + (f", {len(closed)} row(s) closed" if closed else "") + ".")
        return True

    except Exception as e:
        print(f"⚠️  Failed to update the queue for {domain}/{slug}: {e}", file=sys.stderr)
        return False


def add_to_queue(domain: str, product: str, slug: str, langs: List[str], reason: str,
                 source: str = config.SOURCE_MANUAL, priority: str = None,
                 issue: str = config.ISSUE_ISSUE, post_url: str = "", author: str = "") -> List[str]:
    """
    Add a retranslation request to the queue — the one entry point for agents
    and people (CLI: queue_add.py). Languages an open row of the post already
    retranslates (ISSUE or OUTDATED) are skipped, so asking twice doesn't
    duplicate work; the rest go into one new row at the bottom (Priority:
    given, else the issue's default; Missing Since: today). Blank langs = every
    language of the blog, written out in full (since 27 Nov 2026; a blank cell
    was invisible in the sheet and skipped the duplicate check).

    Returns the languages added, [] if nothing was new, or None if the queue
    couldn't be read or written. Never raises.
    """
    try:
        ws = get_scan_worksheet(domain)
        if not ws:
            return None
        values = ws.get_all_values()
        header, rows = queue.from_values(values)
        if not header:
            header = list(config.HEADERS_QUEUE)
        header = queue.merged_header(header, config.HEADERS_QUEUE)

        retranslating = {config.ISSUE_ISSUE, config.ISSUE_OUTDATED}
        tracked = set()
        for row in rows:
            if (row.get(config.KEY_DOMAIN) == domain and row.get(config.KEY_PRODUCT_NAME) == product
                    and row.get(config.KEY_DIR_BASE) == slug and queue.is_open(row)
                    and row.get(config.KEY_ISSUE) in retranslating):
                tracked.update(queue.split_langs(row.get(config.KEY_MISSING_FILES)))

        wanted = list(dict.fromkeys(l.strip() for l in langs if l.strip()))
        if not wanted:              # every language of the blog, listed so people can see it
            wanted = [l for l in config.domains_data[domain][config.KEY_SUPPORTED_LANGS].split("|") if l]
        new = [l for l in wanted if l not in tracked]
        if not new:
            print(f"ℹ️  {domain}/{product}/{slug}: {', '.join(wanted)} already queued for retranslation.")
            return []

        today = datetime.now().astimezone().isoformat()
        row = {h: "" for h in header}
        row.update({
            config.KEY_SCAN_DATE: "", config.KEY_MISSING_SINCE: today[:10], config.KEY_DAYS_MISSING: "0",
            config.KEY_PRIORITY: priority or config.DEFAULT_PRIORITY.get(issue, config.PRIORITY_NORMAL),
            config.KEY_DOMAIN: domain, config.KEY_PRODUCT_NAME: product, config.KEY_DIR_BASE: slug,
            config.KEY_POST_URL: post_url, config.KEY_AUTHOR: author, config.KEY_ISSUE: issue,
            config.KEY_MISSING_COUNT: str(len(new)), config.KEY_MISSING_FILES: queue.join_langs(new),
            config.KEY_ACTION: config.ISSUE_ACTIONS.get(issue, ""), config.KEY_SOURCE: source,
            config.KEY_NOTES: issue_note(reason, source),   # headline = reason, then 'Requested by …'
        })
        old_header = [str(h).strip() for h in values[0]] if values else []
        if header != old_header:            # new tab, or columns missing: write the header first
            ws.update([header], "A1", value_input_option="RAW")
        ws.append_rows(queue.to_values([row], header), value_input_option="RAW")
        print(f"✅ Queued {domain}/{product}/{slug} for retranslation: {', '.join(new)}.")
        return new
    except Exception as e:
        print(f"❌ Could not add {domain}/{product}/{slug} to the queue: {e}", file=sys.stderr)
        return None


def _ensure_history_columns(ws: gspread.Worksheet) -> None:
    """
    Add any HISTORY_HEADERS missing from an existing history tab (e.g. 'Source'
    on a tab created before that column existed), widening the grid if needed.
    """
    header = ws.row_values(1)
    missing = [h for h in HISTORY_HEADERS if h not in header]
    if not missing:
        return
    needed = len(header) + len(missing)
    if ws.col_count < needed:
        ws.add_cols(needed - ws.col_count)
    ws.update([missing], f"{gspread.utils.rowcol_to_a1(1, len(header) + 1)}", value_input_option="RAW")
    print(f"✅ Added column(s) {missing} to '{HISTORY_TAB}' worksheet.")


def _get_history_worksheet() -> gspread.Worksheet:
    """Return the 'history' worksheet, creating it if it doesn't exist."""
    sh = _open_scan_sheet()
    if not sh:
        return None
    try:
        try:
            ws = sh.worksheet(HISTORY_TAB)
            _ensure_history_columns(ws)
            return ws
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=HISTORY_TAB, rows=5000, cols=len(HISTORY_HEADERS))
            ws.update([HISTORY_HEADERS], "A1", value_input_option="RAW")
            print(f"✅ Created '{HISTORY_TAB}' worksheet.")
            return ws
    except Exception as e:
        print(f"❌ Could not open history worksheet: {e}", file=sys.stderr)
        return None


def write_to_google_spreadsheet(
    spreadsheet_id: str,
    valid_extensions: str,
    column_headers: List[list],
    data_to_write: List[list],
    worksheet_name = datetime.now().strftime("%Y-%m-%d")
) -> Union[str, None]:
    """
    Opens a Google Spreadsheet by ID, manages a date-named worksheet within it,
    writes headers and data, moves the worksheet to the first position,
    auto-adjusts column widths, makes the header row bold,
    and returns the URL of the specific worksheet.

    Args:
        spreadsheet_id (str): The ID (or key) of the Google Spreadsheet to open.
        column_headers (List[str]): A list of strings representing the column headers.
        data_to_write (List[list]): A list of lists, where each inner list
                                     represents a row of data to be written.

    Returns:
        Union[str, None]: The URL of the created/updated worksheet, or None if an error occurs.
    """
    # Get the current date to use as the worksheet name (e.g., "2025-06-10").
    # This will be '2025-06-10' as per the current date.
    # current_date_str = datetime.now().strftime("%Y-%m-%d")
    # worksheet_name = current_date_str
    print_on_console(f"Target Worksheet Name: {worksheet_name}")

    try:
        # 1. Authenticate with the Google Sheets API.
        gc = get_gc() # Google Crednetials
        if gc is None:
            print("Failed to initialize Google Sheets client.", file=sys.stderr)
            return None
        
        print_on_console("Authentication successful.")

        # 2. Open the main spreadsheet using its ID/key.
        spreadsheet = gc.open_by_key(spreadsheet_id)
        print_on_console(f"Spreadsheet '{spreadsheet.title}' opened.")

        worksheet_exists = False
        target_worksheet = None # Initialize to None

        try:
            # 3. Try to open the worksheet by its date-based name.
            target_worksheet = spreadsheet.worksheet(worksheet_name)
            worksheet_exists = True
            print_on_console(f"Worksheet '{worksheet_name}' found within the spreadsheet.")
        except gspread.exceptions.WorksheetNotFound:
            # 4. If the worksheet doesn't exist, create a new one.
            print_on_console(f"Worksheet '{worksheet_name}' not found. Creating a new worksheet...")
            # Defaulting to 100 rows and 20 columns for a reasonable starting size.
            target_worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=100, cols=20)
            print_on_console(f"New worksheet '{worksheet_name}' created.")

        # --- Corrected Feature: Move the sheet to the first position ---
        # Get all worksheets in their current order
        all_worksheets = spreadsheet.worksheets()

        # Check if the target worksheet is already at the first position.
        # Compare by ID to ensure it's the exact same sheet object.
        if all_worksheets and all_worksheets[0].id == target_worksheet.id:
            print_on_console(f"Worksheet '{worksheet_name}' is already at the first position.")
        else:
            # Remove the target worksheet from its current position in the list
            # (it might be anywhere, including not yet in 'all_worksheets' if just created)
            # We filter instead of remove() to avoid ValueError if it wasn't there yet.
            reordered_sheets = [ws for ws in all_worksheets if ws.id != target_worksheet.id]
            
            # Insert the target worksheet at the beginning of the list
            reordered_sheets.insert(0, target_worksheet)

            # Reorder the sheets in the spreadsheet
            spreadsheet.reorder_worksheets(reordered_sheets)
            print_on_console(f"Worksheet '{worksheet_name}' moved to the first position.")


        # 5. If the worksheet already existed, clear all its content before writing new data.
        if worksheet_exists and spreadsheet_id != config.SHEET_ID_SUMMARY:
            target_worksheet.clear()
            print_on_console("Existing worksheet content cleared.")

        # 6. Write the defined column headers to the first row.
        if valid_extensions:
            langs_with_commas = valid_extensions.replace("|", ", ")
            target_worksheet.append_row(["Language Support: ", langs_with_commas])

        # 7. Write the defined column headers to the first row.
        if worksheet_exists and spreadsheet_id == config.SHEET_ID_SUMMARY:
            print_on_console("Not writing headers to existing SUMMARY SHEET.")
        else:
            target_worksheet.append_row(column_headers)
            print_on_console("Headers written.")
        
        # --- Format the header row (make it bold) dynamically ---
        # Determine the last column letter based on the number of headers
        last_column_letter = chr(ord('A') + len(column_headers) - 1)
        
        if valid_extensions:
            header_range = f'A2:{last_column_letter}2' # e.g., 'A1:E1' if len(column_headers) is 5
        else:
            header_range = f'A1:{last_column_letter}1' # e.g., 'A1:E1' if len(column_headers) is 5

        header_format = cellFormat(textFormat=textFormat(bold=True))
        format_cell_range(target_worksheet, header_range, header_format)
        print_on_console(f"Header row '{header_range}' formatted (bold).")

        # 8. Append the data rows.
        target_worksheet.append_rows(data_to_write)
        print_on_console(f"{len(data_to_write)} data rows successfully written to worksheet '{worksheet_name}'.")

        # --- Auto-resize columns ---
        target_worksheet.columns_auto_resize(0, len(column_headers))  # Resize all columns
        print_on_console("Columns auto-resized.")

        # 9. Construct and return the URL for the specific worksheet.
        base_spreadsheet_url = spreadsheet.url.split('#')[0]
        worksheet_url = f"{base_spreadsheet_url}#gid={target_worksheet.id}"

        print_on_console(f"\nWorksheet URL: {worksheet_url}")
        return worksheet_url

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Spreadsheet with ID '{spreadsheet_id}' not found. "
              "Please double-check the ID and ensure the service account has access.")
        return None
    except gspread.exceptions.APIError as e:
        print(f"Google Sheets API Error: {e.response.text}")
        print("Please ensure the Google Sheets API is enabled for your project and "
              "your service account has appropriate permissions for the spreadsheet.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

# ======================================================================================
# Read Function
# ======================================================================================

def read_from_google_spreadsheet(spreadsheet_id: str) -> List[list]:
    """
    Reads all data from the first worksheet of a Google Spreadsheet by ID.

    Args:
        spreadsheet_id (str): The ID (or key) of the Google Spreadsheet to read from.

    Returns:
        List[list]: A list of lists representing the rows of data in the worksheet.
                     Returns an empty list if an error occurs.
    """
    try:
        gc = get_gc() # Google Crednetials
        if gc is None:
            print("Failed to initialize Google Sheets client.", file=sys.stderr)
            return None

        print_on_console("Authentication successful.")

        # 2. Open the main spreadsheet using its ID/key.
        spreadsheet = gc.open_by_key(spreadsheet_id)
        print_on_console(f"Spreadsheet '{spreadsheet.title}' opened.")

        # 3. Get the first worksheet (assuming the target data is there, as per write function behavior).
        worksheet = spreadsheet.get_worksheet(0)
        print_on_console(f"Reading from worksheet '{worksheet.title}'.")

        # 4. Read all values from the worksheet.
        data = worksheet.get_all_values()
        print_on_console(f"Read {len(data)} rows from the worksheet.")

        # Skip the first 2 rows (language support and headers) to return only the data rows.
        if len(data) > 2:
            return data[2:]
        else:
            return []

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Spreadsheet with ID '{spreadsheet_id}' not found. "
              "Please double-check the ID and ensure the service account has access.")
        return []
    except gspread.exceptions.APIError as e:
        print(f"Google Sheets API Error: {e.response.text}")
        print("Please ensure the Google Sheets API is enabled for your project and "
              "your service account has appropriate permissions for the spreadsheet.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []
# Printing ======================================
def print_on_console(output):
    if printing_allowed:
        print(output)
# ===============================================
if __name__ == "__main__":
    # --- Example Usage (when called directly as a script) ---
    # Replace with your actual Spreadsheet ID/Key
    
    # --- Configuration ---
    my_spreadsheet_id_key = config.SHEET_ID_GROUPDOCS_COM

    # --- Fixed Column Headers
    # Define the column headers for your spreadsheet.
    column_headers = ["Date", "Domain", "Invalid folder Count", "Authors", "Details Spreadsheet"]

    # Example data rows to be appended
    my_data_rows = [
        ["2025-05-31", "blog.ase.com", 133, "@mshankk", "https://docs.google.com/spreadsheets/d/xx?"],
        ["2025-05-31", "blog.gd.com", 19, "@mshankk", "https://docs.google.com/sheets/d/yy?"]
    ]

    # Call the function with the desired spreadsheet ID/key and data
    sheet_link = write_to_google_spreadsheet(my_spreadsheet_id_key, column_headers, my_data_rows)

    if sheet_link:
        print(f"\nOperation completed successfully. Access the worksheet at: {sheet_link}")
    else:
        print("\nOperation failed to complete successfully.")