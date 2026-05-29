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
            print("✅ GSheets client initialized using GitHub Secret.")
            
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