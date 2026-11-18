"""
Tests for the one-time queue reset (reset_scan_queue.py): which history rows
are deleted, bottom-up row deletion, and the dry-run / apply flow against a
fake spreadsheet.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import io_google_spreadsheet as gs
import reset_scan_queue as reset
from fake_sheet import FakeWorksheet


def hist(domain, status, slug="p"):
    row = dict.fromkeys(gs.HISTORY_HEADERS, "")
    row.update({"Domain": domain, "Status": status, "Blog Post Directory": slug})
    return [row[h] for h in gs.HISTORY_HEADERS]


HISTORY = [
    gs.HISTORY_HEADERS,
    hist("blog.aspose.com", "completed", "keep1"),       # 2
    hist("blog.aspose.com", "pending"),                  # 3
    hist("blog.aspose.com", "partial"),                  # 4
    hist("blog.groupdocs.com", "completed"),             # 5
    hist("blog.aspose.cloud", "completed", "keep2"),     # 6
    [""] * len(gs.HISTORY_HEADERS),                      # 7 (blank: ignored)
    hist("blog.groupdocs.com", "pending"),               # 8
]


class TestHistoryRowsToDelete:
    def test_pending_partial_and_groupdocs_com(self):
        assert reset.history_rows_to_delete(HISTORY) == [3, 4, 5, 8]

    def test_empty_tab(self):
        assert reset.history_rows_to_delete([]) == []

    def test_ranges_bottom_up(self):
        assert reset.contiguous_ranges([2, 3, 4, 7, 9, 10]) == [(9, 10), (7, 7), (2, 4)]
        assert reset.contiguous_ranges([]) == []

    def test_delete_requests_are_zero_based_end_exclusive(self):
        (req,) = reset.delete_rows_requests(5, [3, 4])
        assert req["deleteDimension"]["range"] == {"sheetId": 5, "dimension": "ROWS",
                                                   "startIndex": 2, "endIndex": 4}


class FakeSheet:
    def __init__(self, tabs):
        self.tabs = tabs
        self.duplicated = []
        for i, ws in enumerate(tabs):
            ws.id = i
            ws.spreadsheet.sheet = self

    def worksheets(self):
        return list(self.tabs)

    def duplicate_sheet(self, sheet_id, new_sheet_name=None):
        self.duplicated.append(new_sheet_name)

    def batch_update(self, body):
        ws = next(t for t in self.tabs if t.id == body["requests"][0]["deleteDimension"]["range"]["sheetId"])
        ws.spreadsheet.batch_update(body)


def make_sheet():
    history = FakeWorksheet(HISTORY, title="history")
    domain = FakeWorksheet([["Scan Date"] + config.HEADERS_SCAN_RESULTS, ["d", "blog.aspose.com", "x"]],
                           title="blog.aspose.com")
    cleanup = FakeWorksheet([config.HEADERS_CLEANUP, ["d", "blog.aspose.com"]], title="cleanup")
    other = FakeWorksheet([["keep"]], title="notes")
    return FakeSheet([history, domain, cleanup, other])


class TestMain:
    def test_dry_run_changes_nothing(self, monkeypatch, capsys):
        sheet = make_sheet()
        before = [ws.get_all_values() for ws in sheet.tabs]
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: sheet)
        assert reset.main([]) == 0
        assert [ws.get_all_values() for ws in sheet.tabs] == before
        assert sheet.duplicated == []
        assert "DRY RUN" in capsys.readouterr().out

    def test_apply_backs_up_then_resets(self, monkeypatch):
        sheet = make_sheet()
        history, domain, cleanup, other = sheet.tabs
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: sheet)
        assert reset.main(["--apply"]) == 0

        assert len(sheet.duplicated) == 3 and all(n.startswith("bak-") for n in sheet.duplicated)
        assert [r[gs.HISTORY_HEADERS.index("Blog Post Directory")] for r in history.get_all_values()[1:]] \
            == ["keep1", "keep2"]
        assert domain.get_all_values() == [config.HEADERS_QUEUE]
        assert cleanup.get_all_values() == [config.HEADERS_CLEANUP]
        assert other.get_all_values() == [["keep"]]

    def test_no_sheet_access_fails(self, monkeypatch):
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: None)
        assert reset.main([]) == 1
