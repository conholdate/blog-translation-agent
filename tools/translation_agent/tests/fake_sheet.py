"""
An in-memory stand-in for a gspread Worksheet, for the sheet tests.

Supports what io_google_spreadsheet and reset_scan_queue use: reading values,
A1-range updates, batch updates / clears, appends, resizing and row deletion
(spreadsheet.batch_update with deleteDimension). Every write is recorded in
.calls as (method, range or None, value_input_option).
"""

from gspread.utils import a1_range_to_grid_range


class FakeSpreadsheet:
    url = "https://docs.google.com/spreadsheets/d/SHEET"

    def __init__(self, ws):
        self.ws = ws
        self.requests = []

    def batch_update(self, body):
        for req in body.get("requests", []):
            self.requests.append(req)
            if "deleteDimension" in req:
                rng = req["deleteDimension"]["range"]
                del self.ws.rows[rng["startIndex"]:rng["endIndex"]]


class FakeWorksheet:
    def __init__(self, rows=None, title="tab", row_count=1000, col_count=26, sheet_id=7):
        self.rows = [list(r) for r in (rows or [])]
        self.title = title
        self.row_count = row_count
        self.col_count = col_count
        self.id = sheet_id
        self.calls = []
        self.spreadsheet = FakeSpreadsheet(self)

    # --- reads ---
    def get_all_values(self):
        width = max((len(r) for r in self.rows), default=0)
        rows = [list(r) + [""] * (width - len(r)) for r in self.rows]
        while rows and not any(str(v) for v in rows[-1]):       # Sheets drops trailing empty rows
            rows.pop()
        return rows

    def row_values(self, i):
        row = list(self.rows[i - 1]) if i <= len(self.rows) else []
        while row and row[-1] == "":
            row.pop()
        return row

    # --- writes ---
    def _set(self, r0, c0, values):
        for i, vals in enumerate(values):
            while len(self.rows) <= r0 + i:
                self.rows.append([])
            row = self.rows[r0 + i]
            for j, v in enumerate(vals):
                row += [""] * (c0 + j + 1 - len(row))
                row[c0 + j] = v

    def update(self, values, range_name="A1", value_input_option=None):
        self.calls.append(("update", range_name, value_input_option))
        g = a1_range_to_grid_range(range_name)
        self._set(g.get("startRowIndex", 0), g.get("startColumnIndex", 0), values)

    def batch_update(self, updates, value_input_option=None):
        for u in updates:
            self.calls.append(("batch_update", u["range"], value_input_option))
            g = a1_range_to_grid_range(u["range"])
            self._set(g.get("startRowIndex", 0), g.get("startColumnIndex", 0), u["values"])

    def batch_clear(self, ranges):
        for rng in ranges:
            self.calls.append(("batch_clear", rng, None))
            g = a1_range_to_grid_range(rng)
            for r in range(g.get("startRowIndex", 0), min(g.get("endRowIndex", len(self.rows)), len(self.rows))):
                row = self.rows[r]
                for c in range(g.get("startColumnIndex", 0), min(g.get("endColumnIndex", len(row)), len(row))):
                    row[c] = ""

    def clear(self):
        self.calls.append(("clear", None, None))
        self.rows = []

    def append_rows(self, rows, value_input_option=None):
        self.calls.append(("append_rows", None, value_input_option))
        self.rows = self.get_all_values() + [list(r) for r in rows]

    def resize(self, rows=None, cols=None):
        self.calls.append(("resize", None, None))
        self.row_count = rows or self.row_count
        self.col_count = cols or self.col_count

    def add_cols(self, n):
        self.col_count += n
