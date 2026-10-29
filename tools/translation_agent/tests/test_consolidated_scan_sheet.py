"""
Tests for the consolidated scan sheet: the translator's reader
(read_domain_scan_rows) and the scanner's Missing Since / Days Missing columns
(write_domain_scan_results + get_history_first_seen), against fake worksheets.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import config
import io_google_spreadsheet as gs

HEADERS = config.HEADERS_MISSING_TRANSLATIONS


def _scan_row(slug, issue="MISSING", langs="ar, de"):
    return ["blog.aspose.com", "medical", slug, f"blog.aspose.com/medical/{slug}/", "Author",
            issue, str(len(langs.split(","))), langs, "Translate", ""]


class FakeWorksheet:
    def __init__(self, rows=None):
        self.rows = [list(r) for r in (rows or [])]
        self.written = None

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def clear(self):
        self.rows = []

    def update(self, values, value_input_option=None):
        self.written = values
        self.rows = [list(r) for r in values]


# ============================================================================
# read_domain_scan_rows
# ============================================================================

class TestReadDomainScanRows:
    def _patch(self, monkeypatch, ws):
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)

    def test_returns_translator_layout_and_scan_date(self, monkeypatch):
        ws = FakeWorksheet([
            gs.DOMAIN_TAB_LEAD_HEADERS + HEADERS,
            ["2026-10-29T03:49:19+00:00", "2026-10-21", "8"] + _scan_row("p1"),
        ])
        self._patch(monkeypatch, ws)
        rows, scan_date = gs.read_domain_scan_rows("blog.aspose.com")
        assert rows == [_scan_row("p1")]
        assert scan_date.startswith("2026-10-29T03:49")

    def test_columns_found_by_name_not_position(self, monkeypatch):
        # Older tab layout: only Scan Date in front
        ws = FakeWorksheet([["Scan Date"] + HEADERS, ["2026-10-29"] + _scan_row("p1")])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows("blog.aspose.com")
        assert rows == [_scan_row("p1")]

    def test_order_preserved_and_blank_rows_skipped(self, monkeypatch):
        ws = FakeWorksheet([
            ["Scan Date"] + HEADERS,
            ["d"] + _scan_row("first"),
            [""] * (len(HEADERS) + 1),
            ["d"] + _scan_row("second"),
        ])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows("blog.aspose.com")
        assert [r[2] for r in rows] == ["first", "second"]

    def test_manual_split_rows_kept_separate_in_order(self, monkeypatch):
        # A post split by hand (e.g. try 2 languages first) stays split, so a
        # limit=1 run picks only the first part.
        ws = FakeWorksheet([
            ["Scan Date"] + HEADERS,
            ["d"] + _scan_row("split", langs="ar, cs"),
            ["d"] + _scan_row("split", langs="de, fr"),
            ["d"] + _scan_row("other"),
        ])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows("blog.aspose.com")
        assert [(r[2], r[7]) for r in rows] == [("split", "ar, cs"), ("split", "de, fr"), ("other", "ar, de")]

    def test_empty_tab_means_nothing_to_do(self, monkeypatch):
        self._patch(monkeypatch, FakeWorksheet([["Scan Date"] + HEADERS]))
        assert gs.read_domain_scan_rows("blog.aspose.com") == ([], "")

    def test_unreadable_tab_returns_none_for_fallback(self, monkeypatch):
        self._patch(monkeypatch, None)
        assert gs.read_domain_scan_rows("blog.aspose.com") == (None, "")

    def test_missing_required_column_returns_none(self, monkeypatch):
        self._patch(monkeypatch, FakeWorksheet([["Scan Date", "Domain"]]))
        assert gs.read_domain_scan_rows("blog.aspose.com") == (None, "")


# ============================================================================
# write_domain_scan_results + get_history_first_seen
# ============================================================================

class TestMissingSince:
    def test_domain_tab_gets_missing_since_and_days(self, monkeypatch):
        ws = FakeWorksheet()
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        monkeypatch.setattr(gs, "_auto_resize_columns", lambda ws: None)

        first_seen = {("old-post", "MISSING"): "2026-10-21T02:49:09+00:00"}
        ok = gs.write_domain_scan_results(
            "blog.aspose.com", "2026-10-29T03:49:19+00:00",
            [_scan_row("old-post"), _scan_row("new-post")], HEADERS, first_seen=first_seen)

        assert ok
        assert ws.written[0][:4] == ["Scan Date", "Missing Since", "Days Missing", "Domain"]
        assert ws.written[1][:3] == ["2026-10-29T03:49:19+00:00", "2026-10-21", "8"]
        assert ws.written[2][:3] == ["2026-10-29T03:49:19+00:00", "2026-10-29", "0"]   # first seen today

    def test_first_seen_uses_open_history_rows_only(self, monkeypatch):
        hist = FakeWorksheet([
            gs.HISTORY_HEADERS,
            ["2026-09-01", "blog.aspose.com", "medical", "p", "u", "A", "MISSING", "ar", "1", "completed", "2026-09-05", ""],
            ["2026-10-21", "blog.aspose.com", "medical", "p", "u", "A", "MISSING", "ar", "1", "pending", "", ""],
            ["2026-10-22", "blog.aspose.cloud", "email", "q", "u", "A", "MISSING", "ar", "1", "pending", "", ""],
        ])
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: hist)
        assert gs.get_history_first_seen("blog.aspose.com") == {("p", "MISSING"): "2026-10-21"}

    def test_days_between_handles_bad_dates(self):
        assert gs._days_between("", "2026-10-29") == ""
        assert gs._days_between("2026-10-21", "2026-10-29T03:00:00+00:00") == "8"
