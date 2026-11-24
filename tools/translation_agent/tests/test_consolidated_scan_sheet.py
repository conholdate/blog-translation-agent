"""
Tests for the consolidated scan sheet I/O: the translator's queue reader
(read_domain_scan_rows), the scanner's queue sync (sync_domain_queue), the
cleanup tab and the history tab (completed rows only) — against fake worksheets.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import config
import io_google_spreadsheet as gs
from fake_sheet import FakeWorksheet

HEADERS = config.HEADERS_MISSING_TRANSLATIONS
DOMAIN = "blog.aspose.com"
SCAN = "2026-11-18T00:00:00+00:00"


def _scan_row(slug, issue="MISSING", langs="ar, de", status=""):
    return [DOMAIN, "medical", slug, f"{DOMAIN}/medical/{slug}/", "Author",
            issue, str(len(langs.split(","))), langs, config.ISSUE_ACTIONS[issue], status]


def finding(slug, issue="MISSING", langs="ar, de", notes=""):
    return dict(zip(HEADERS + ["Notes"], _scan_row(slug, issue, langs) + [notes]))


def queue_values(*rows, header=config.HEADERS_QUEUE):
    """Queue tab values from dict rows (missing columns blank)."""
    return [header] + [[str(r.get(h, "")) for h in header] for r in rows]


def as_dicts(ws):
    header, rows = gs.queue.from_values(ws.get_all_values())
    return rows


@pytest.fixture(autouse=True)
def no_resize(monkeypatch):
    monkeypatch.setattr(gs, "_auto_resize_columns", lambda ws: None)


# ============================================================================
# read_domain_scan_rows
# ============================================================================

class TestReadDomainScanRows:
    def _patch(self, monkeypatch, ws):
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)

    def test_returns_translator_layout_plus_priority_and_scan_date(self, monkeypatch):
        ws = FakeWorksheet([
            ["Scan Date", "Missing Since", "Days Missing", "Priority"] + HEADERS,
            ["2026-10-29T03:49:19+00:00", "2026-10-21", "8", "Urgent"] + _scan_row("p1"),
        ])
        self._patch(monkeypatch, ws)
        rows, scan_date = gs.read_domain_scan_rows(DOMAIN)
        assert rows == [_scan_row("p1") + ["Urgent", ""]]
        assert scan_date.startswith("2026-10-29T03:49")

    def test_old_tab_without_priority_reads_blank_priority(self, monkeypatch):
        ws = FakeWorksheet([["Scan Date"] + HEADERS, ["2026-10-29"] + _scan_row("p1")])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows(DOMAIN)
        assert rows == [_scan_row("p1") + ["", ""]]

    def test_columns_found_by_name_not_position(self, monkeypatch):
        header = ["Priority", "Notes"] + HEADERS[::-1]
        ws = FakeWorksheet([header, ["Low", "n"] + _scan_row("p1")[::-1]])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows(DOMAIN)
        assert rows == [_scan_row("p1") + ["Low", ""]]

    def test_ready_after_is_returned_as_column_11(self, monkeypatch):
        ws = FakeWorksheet([
            ["Ready After", "Priority"] + HEADERS,
            ["2026-11-22 14:05 UTC", "High"] + _scan_row("p1"),
        ])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows(DOMAIN)
        assert rows[0][10:] == ["High", "2026-11-22 14:05 UTC"]

    def test_order_preserved_and_blank_rows_skipped(self, monkeypatch):
        ws = FakeWorksheet([
            ["Scan Date"] + HEADERS,
            ["d"] + _scan_row("first"),
            [""] * (len(HEADERS) + 1),
            ["d"] + _scan_row("second"),
        ])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows(DOMAIN)
        assert [r[2] for r in rows] == ["first", "second"]

    def test_manual_split_rows_kept_separate_in_order(self, monkeypatch):
        ws = FakeWorksheet([
            ["Scan Date"] + HEADERS,
            ["d"] + _scan_row("split", langs="ar, cs"),
            ["d"] + _scan_row("split", langs="de, fr"),
        ])
        self._patch(monkeypatch, ws)
        rows, _ = gs.read_domain_scan_rows(DOMAIN)
        assert [(r[2], r[7]) for r in rows] == [("split", "ar, cs"), ("split", "de, fr")]

    def test_empty_tab_means_nothing_to_do(self, monkeypatch):
        self._patch(monkeypatch, FakeWorksheet([["Scan Date"] + HEADERS]))
        assert gs.read_domain_scan_rows(DOMAIN) == ([], "")

    def test_unreadable_tab_returns_none(self, monkeypatch):
        self._patch(monkeypatch, None)
        assert gs.read_domain_scan_rows(DOMAIN) == (None, "")

    def test_missing_required_column_returns_none(self, monkeypatch):
        self._patch(monkeypatch, FakeWorksheet([["Scan Date", "Domain"]]))
        assert gs.read_domain_scan_rows(DOMAIN) == (None, "")


# ============================================================================
# sync_domain_queue
# ============================================================================

class TestSyncDomainQueue:
    @pytest.fixture
    def tabs(self, monkeypatch):
        tabs = {"queue": FakeWorksheet([config.HEADERS_QUEUE]),
                "history": FakeWorksheet([gs.HISTORY_HEADERS])}
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: tabs["queue"])
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: tabs["history"])
        return tabs

    def test_first_scan_fills_the_queue(self, tabs):
        res = gs.sync_domain_queue(DOMAIN, [finding("a"), finding("b", "OUTDATED", "fr")], SCAN)
        assert res["ok"] and res["new"] == 2 and res["open"] == 2 and res["closed"] == 0
        assert res["url"].endswith("#gid=7")
        rows = as_dicts(tabs["queue"])
        assert [(r["Blog Post Directory"], r["Priority"]) for r in rows] == [("a", "High"), ("b", "Low")]

    def test_written_raw_so_comments_never_become_formulas(self, tabs):
        gs.sync_domain_queue(DOMAIN, [finding("a")], SCAN)
        assert {opt for m, _, opt in tabs["queue"].calls if m == "update"} == {"RAW"}

    def test_closed_rows_move_to_history_and_leave_the_queue(self, tabs):
        tabs["queue"].rows = queue_values(
            {"Missing Since": "2026-11-01", "Domain": DOMAIN, "Product": "medical",
             "Blog Post Directory": "done", "Issue": "MISSING", "Target Translations": "ar",
             "Comments": "- ✅ Translated 1/1", "Priority": "High", "Source": "Scanner"},
            {"Missing Since": "2026-11-02", "Domain": DOMAIN, "Product": "medical",
             "Blog Post Directory": "a", "Issue": "MISSING", "Target Translations": "ar, de"})
        res = gs.sync_domain_queue(DOMAIN, [finding("a")], SCAN)
        assert res["closed"] == 1
        assert [r["Blog Post Directory"] for r in as_dicts(tabs["queue"])] == ["a"]
        (hist,) = as_dicts(tabs["history"])
        assert hist["Blog Post Directory"] == "done" and hist["Status"] == "completed"
        assert hist["Scan Date"] == "2026-11-01"            # first flagged
        assert hist["Completed Date"] == SCAN
        assert hist["Comments"] == "- ✅ Translated 1/1" and hist["Source"] == "Scanner"

    def test_leftover_rows_below_are_blanked(self, tabs):
        tabs["queue"].rows = queue_values(*[
            {"Domain": DOMAIN, "Product": "medical", "Blog Post Directory": s, "Issue": "MISSING",
             "Target Translations": "ar"} for s in ("x", "y", "z")])
        gs.sync_domain_queue(DOMAIN, [], SCAN)
        assert tabs["queue"].get_all_values() == [config.HEADERS_QUEUE]

    def test_people_added_columns_are_kept(self, tabs):
        header = ["Owner"] + config.HEADERS_QUEUE
        tabs["queue"].rows = queue_values(
            {"Owner": "Sam", "Domain": DOMAIN, "Product": "medical", "Blog Post Directory": "a",
             "Issue": "MISSING", "Target Translations": "ar, de"}, header=header)
        gs.sync_domain_queue(DOMAIN, [finding("a")], SCAN)
        assert tabs["queue"].get_all_values()[0][0] == "Owner"
        assert as_dicts(tabs["queue"])[0]["Owner"] == "Sam"

    def test_old_format_tab_gets_the_new_columns(self, tabs):
        tabs["queue"].rows = [["Scan Date"] + HEADERS, ["d"] + _scan_row("a")]
        gs.sync_domain_queue(DOMAIN, [finding("a")], SCAN)
        header = tabs["queue"].get_all_values()[0]
        assert {"Priority", "Source", "Missing Since", "Comments"} <= set(header)

    def test_groupdocs_com_closed_rows_are_dropped_not_historied(self, tabs, monkeypatch):
        tabs["queue"].rows = queue_values(
            {"Domain": "blog.groupdocs.com", "Product": "viewer", "Blog Post Directory": "done",
             "Issue": "MISSING", "Target Translations": "ar"})
        res = gs.sync_domain_queue("blog.groupdocs.com", [], SCAN)
        assert res["closed"] == 1
        assert tabs["history"].get_all_values() == [gs.HISTORY_HEADERS]

    def test_unreadable_queue_reports_not_ok(self, monkeypatch):
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: None)
        assert gs.sync_domain_queue(DOMAIN, [finding("a")], SCAN)["ok"] is False

    def test_write_failure_reports_not_ok_and_keeps_the_tab(self, tabs, monkeypatch):
        tabs["queue"].rows = queue_values({"Domain": DOMAIN, "Product": "medical",
                                           "Blog Post Directory": "a", "Issue": "MISSING",
                                           "Target Translations": "ar"})
        before = tabs["queue"].get_all_values()

        def boom(*a, **k):
            raise RuntimeError("quota")
        monkeypatch.setattr(tabs["queue"], "update", boom)
        assert gs.sync_domain_queue(DOMAIN, [], SCAN)["ok"] is False
        assert tabs["queue"].get_all_values() == before


# ============================================================================
# cleanup tab
# ============================================================================

class TestCleanupTab:
    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet([config.HEADERS_CLEANUP,
                            ["old", "blog.aspose.cloud"] + _scan_row("keep", "EXTRA", "tmp")[1:] + ["n"],
                            ["old"] + _scan_row("stale", "EXTRA", "tmp") + ["n"]])
        monkeypatch.setattr(gs, "_get_or_create_tab", lambda title, header, rows=1000: ws)
        return ws

    def test_replaces_only_this_domains_rows(self, ws):
        assert gs.replace_cleanup_rows(DOMAIN, [finding("new", "EXTRA", "cs")], SCAN)
        rows = as_dicts(ws)
        assert [(r["Domain"], r["Blog Post Directory"]) for r in rows] == [
            ("blog.aspose.cloud", "keep"), (DOMAIN, "new")]
        assert rows[1]["Scan Date"] == SCAN

    def test_read_cleanup_rows_for_one_domain(self, ws, monkeypatch):
        class Sheet:
            def worksheet(self, title):
                return ws
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: Sheet())
        assert gs.read_cleanup_rows(DOMAIN) == [_scan_row("stale", "EXTRA", "tmp")]

    def test_read_cleanup_rows_without_tab(self, monkeypatch):
        import gspread

        class Sheet:
            def worksheet(self, title):
                raise gspread.exceptions.WorksheetNotFound(title)
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: Sheet())
        assert gs.read_cleanup_rows(DOMAIN) == []


# ============================================================================
# history tab
# ============================================================================

class TestHistoryTab:
    def test_append_maps_columns_by_name(self, monkeypatch):
        ws = FakeWorksheet([["Domain", "Scan Date", "Status", "Mine"]])
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: ws)
        assert gs.append_history_rows(DOMAIN, [{"Domain": DOMAIN, "Missing Since": "2026-11-01",
                                                "Status": "completed"}])
        assert ws.get_all_values()[1] == [DOMAIN, "2026-11-01", "completed", ""]
        assert ws.calls[-1] == ("append_rows", None, "RAW")

    def test_append_never_raises(self, monkeypatch):
        def boom():
            raise RuntimeError("down")
        monkeypatch.setattr(gs, "_get_history_worksheet", boom)
        assert gs.append_history_rows(DOMAIN, [{"Domain": DOMAIN}]) is False

    def test_ensure_history_columns_adds_priority_and_source(self):
        ws = FakeWorksheet([gs.HISTORY_HEADERS[:-2]], col_count=13)
        gs._ensure_history_columns(ws)
        assert ws.row_values(1) == gs.HISTORY_HEADERS
        assert ws.col_count == 15


# ============================================================================
# add_to_queue
# ============================================================================

class TestAddToQueue:
    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet(queue_values(
            {"Domain": DOMAIN, "Product": "medical", "Blog Post Directory": "p", "Issue": "OUTDATED",
             "Target Translations": "fr"},
            {"Domain": DOMAIN, "Product": "medical", "Blog Post Directory": "p", "Issue": "ISSUE",
             "Target Translations": "de", "Status": "hold"}))
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        return ws

    def test_adds_an_issue_row_at_the_bottom(self, ws):
        assert gs.add_to_queue(DOMAIN, "medical", "p", ["it", "ja"], "tables in English",
                               source="quality-agent") == ["it", "ja"]
        row = as_dicts(ws)[-1]
        assert row["Issue"] == "ISSUE" and row["Action"] == "Retranslate"
        assert row["Target Translations"] == "it, ja" and row["Count"] == "2"
        assert row["Priority"] == "Normal" and row["Source"] == "quality-agent"
        assert row["Notes"] == "tables in English\nRequested by quality-agent" and row["Missing Since"]
        assert ws.calls[-1] == ("append_rows", None, "RAW")

    def test_languages_already_being_retranslated_are_skipped(self, ws):
        assert gs.add_to_queue(DOMAIN, "medical", "p", ["fr", "it"], "x") == ["it"]
        assert gs.add_to_queue(DOMAIN, "medical", "p", ["fr"], "x") == []

    def test_held_rows_do_not_count(self, ws):
        assert gs.add_to_queue(DOMAIN, "medical", "p", ["de"], "x") == ["de"]

    def test_priority_and_all_languages(self, ws):
        assert gs.add_to_queue(DOMAIN, "medical", "p", [], "x", priority="Urgent") == ["(all)"]
        row = as_dicts(ws)[-1]
        assert row["Priority"] == "Urgent" and row["Target Translations"] == ""

    def test_empty_tab_gets_a_header(self, monkeypatch):
        ws = FakeWorksheet([])
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        gs.add_to_queue(DOMAIN, "medical", "p", ["fr"], "x")
        assert ws.get_all_values()[0] == config.HEADERS_QUEUE and len(ws.get_all_values()) == 2

    def test_unreadable_queue_returns_none(self, monkeypatch):
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: None)
        assert gs.add_to_queue(DOMAIN, "medical", "p", ["fr"], "x") is None


class TestQueueAddCli:
    def test_rejects_unsupported_language(self, monkeypatch):
        import queue_add
        monkeypatch.setattr(gs, "add_to_queue", lambda *a, **k: pytest.fail("must not write"))
        assert queue_add.main(["--domain", DOMAIN, "--post", "pdf/p", "--langs", "xx", "--reason", "r"]) == 2

    def test_dry_run_writes_nothing(self, monkeypatch):
        import queue_add
        monkeypatch.setattr(gs, "add_to_queue", lambda *a, **k: pytest.fail("must not write"))
        assert queue_add.main(["--domain", DOMAIN, "--post", "pdf/p", "--reason", "r", "--dry-run"]) == 0

    def test_passes_parsed_post(self, monkeypatch):
        import queue_add
        seen = {}
        monkeypatch.setattr(gs, "add_to_queue", lambda *a, **k: seen.update(args=a, kw=k) or ["fr"])
        assert queue_add.main(["--domain", DOMAIN, "--post", "content/Aspose.Blog/pdf/p/",
                               "--langs", "fr", "--reason", "r", "--source", "bot"]) == 0
        assert seen["args"][:4] == (DOMAIN, "pdf", "p", ["fr"]) and seen["kw"]["source"] == "bot"
