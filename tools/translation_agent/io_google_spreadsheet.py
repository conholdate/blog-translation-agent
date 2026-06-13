import os
import json
import gspread
import sys
import gspread
import config
from datetime import datetime
from typing import List, Union # For type hints and better readability
from gspread_formatting import cellFormat, textFormat, format_cell_range # Explicitly import necessary functions/classes

# --- Global Configuration (remains here as it's typically environment-specific) ---
# Path to your Google service account JSON key file.
# Make sure this file is secure and its path is correct.    
# 1. Try to load JSON content from the environment variable
json_content = os.getenv("GOOGLE_CREDENTIALS_JSON_SK")
BASE_DIR = os.getenv("GITHUB_WORKSPACE", os.getcwd())

printing_allowed = False

# History tab constants
HISTORY_TAB             = "history"
HISTORY_HEADERS         = [
    "Scan Date", "Domain", "Product", "Blog Post Directory",
    "Blog Post URL", "Author", "Missing Translations", "Missing Count",
    "Status", "Completed Date",
]
HISTORY_STATUS_PENDING   = "pending"
HISTORY_STATUS_PARTIAL   = "partial"
HISTORY_STATUS_COMPLETED = "completed"

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
            print("✅ GSheets client initialized.")
            
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


def write_domain_scan_results(domain: str, scan_date: str, rows: List[list], headers: List[str]) -> bool:
    """
    Overwrite the domain tab in the consolidated scan sheet with the latest scan results.

    - Prepends 'Scan Date' as the first column on both the header row and every data row.
    - Clears all existing content before writing.

    Returns True on success, False on failure.
    """
    ws = get_scan_worksheet(domain)
    if not ws:
        return False

    try:
        # Build header and data with Scan Date prepended
        header_row = ["Scan Date"] + headers
        data_rows  = [[scan_date] + row for row in rows]

        ws.clear()
        ws.update([header_row] + data_rows, value_input_option="USER_ENTERED")
        _auto_resize_columns(ws)

        print(f"✅ Scan results written to '{domain}' tab ({len(data_rows)} rows).")
        return True

    except Exception as e:
        print(f"❌ Failed to write scan results for '{domain}': {e}", file=sys.stderr)
        return False


def _get_history_worksheet() -> gspread.Worksheet:
    """Return the 'history' worksheet, creating it if it doesn't exist."""
    gc = get_scan_gc()
    if not gc:
        return None
    try:
        sh = gc.open_by_key(config.TRANSLATION_SCAN_SHEET_ID)
        try:
            return sh.worksheet(HISTORY_TAB)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=HISTORY_TAB, rows=5000, cols=len(HISTORY_HEADERS))
            ws.append_row(HISTORY_HEADERS, value_input_option="USER_ENTERED")
            print(f"✅ Created '{HISTORY_TAB}' worksheet.")
            return ws
    except Exception as e:
        print(f"❌ Could not open history worksheet: {e}", file=sys.stderr)
        return None


def update_history_tab(domain: str, scan_date: str, current_rows: List[list]) -> bool:
    """
    Update the history tab with the latest scan results for a domain.

    current_rows must match HEADERS_MISSING_TRANSLATIONS column order:
    [domain, product, slug, url, author, missing_count, missing_langs, extra, extra_count, status]

    Logic per existing history row (Status != completed):
      - Post gone from current scan   → Status = completed, Completed Date = scan_date
      - Post present, fewer languages → Status = partial,   update Missing Translations
      - Post present, same languages  → no change

    New posts not yet in history → appended as pending.
    """
    ws = _get_history_worksheet()
    if not ws:
        return False

    try:
        all_rows = ws.get_all_values()
        data_rows = all_rows[1:] if len(all_rows) > 1 else []   # skip header

        # Column indices inside a history row (0-based)
        C_SLUG    = 3
        C_DOMAIN  = 1
        C_LANGS   = 6
        C_COUNT   = 7
        C_STATUS  = 8
        C_DONE    = 9

        # Build lookup from current scan keyed by (domain, slug)
        # current_rows: [domain(0), product(1), slug(2), url(3), author(4),
        #                missing_count(5), missing_langs(6), extra(7), extra_count(8), status(9)]
        current_lookup = {
            (r[0], r[2]): r
            for r in current_rows
            if len(r) >= 7 and r[0] and r[2]
        }

        batch_updates = []
        seen_keys     = set()

        for i, row in enumerate(data_rows):
            row = list(row) + [""] * (len(HISTORY_HEADERS) - len(row))  # pad short rows

            if row[C_DOMAIN] != domain:
                continue
            if row[C_STATUS] == HISTORY_STATUS_COMPLETED:
                continue

            key = (row[C_DOMAIN], row[C_SLUG])
            seen_keys.add(key)
            sheet_row = i + 2   # +1 header, +1 for 1-indexed

            if key in current_lookup:
                cur = current_lookup[key]
                # Languages still missing across the whole post (from current scan)
                cur_langs  = {l.strip() for l in str(cur[6]).split(",") if l.strip()}
                # Languages this specific history row was tracking
                hist_langs = {l.strip() for l in row[C_LANGS].split(",")  if l.strip()}

                # Which of this row's langs are still missing?
                remaining = hist_langs & cur_langs

                if not remaining:
                    # All langs in this row are now translated
                    row[C_STATUS] = HISTORY_STATUS_COMPLETED
                    row[C_DONE]   = scan_date
                    batch_updates.append({"range": f"A{sheet_row}", "values": [row]})
                elif remaining < hist_langs:
                    # Some langs in this row are still missing
                    remaining_str = ", ".join(sorted(remaining))
                    row[C_LANGS]  = remaining_str
                    row[C_COUNT]  = str(len(remaining))
                    row[C_STATUS] = HISTORY_STATUS_PARTIAL
                    batch_updates.append({"range": f"A{sheet_row}", "values": [row]})
                # else: remaining == hist_langs → all still missing, no change
            else:
                # Post is completely gone from the missing list
                row[C_STATUS] = HISTORY_STATUS_COMPLETED
                row[C_DONE]   = scan_date
                batch_updates.append({"range": f"A{sheet_row}", "values": [row]})

        if batch_updates:
            ws.batch_update(batch_updates, value_input_option="USER_ENTERED")

        # Append rows for posts not yet in history
        new_rows = [
            [
                scan_date, r[0], r[1], r[2], r[3], r[4],
                r[6], str(r[5]), HISTORY_STATUS_PENDING, "",
            ]
            for r in current_rows
            if len(r) >= 7 and r[0] and r[2]
            and (r[0], r[2]) not in seen_keys
        ]

        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")

        _auto_resize_columns(ws)

        print(f"✅ History updated for '{domain}': {len(batch_updates)} updated, {len(new_rows)} new.")
        return True

    except Exception as e:
        print(f"❌ Failed to update history for '{domain}': {e}", file=sys.stderr)
        return False


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