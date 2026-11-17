"""
Tests for update_history_tab() — how each scan updates the history tab:
new rows, partial / completed rows, OUTDATED rows tracked apart from MISSING,
and the Notes column. Uses a fake worksheet that records how cells were written.
"""

import pytest
from gspread.utils import a1_range_to_grid_range

import config
import io_google_spreadsheet as gs

DOMAIN = "blog.aspose.com"
SCAN = "2026-11-17T03:00:00+00:00"


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.calls = []          # (value_input_option, range)

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def batch_update(self, updates, value_input_option=None):
        for u in updates:
            self.calls.append((value_input_option, u["range"]))
            g = a1_range_to_grid_range(u["range"])
            for i, values in enumerate(u["values"]):
                r = self.rows[g["startRowIndex"] + i]
                for j, v in enumerate(values):
                    c = g["startColumnIndex"] + j
                    r += [""] * (c + 1 - len(r))
                    r[c] = v

    def append_rows(self, rows, value_input_option=None):
        self.rows += [list(r) for r in rows]


def scan_row(slug, issue=config.ISSUE_MISSING, langs="de, fr", notes=""):
    action = {config.ISSUE_MISSING: config.ACTION_TRANSLATE,
              config.ISSUE_OUTDATED: config.ACTION_RETRANSLATE}.get(issue, config.ACTION_DELETE)
    return [DOMAIN, "words", slug, f"{DOMAIN}/words/{slug}/", "Jane", issue,
            str(len(langs.split(","))), langs, action, "", notes]


def hist_row(slug, issue=config.ISSUE_MISSING, langs="de, fr", status="pending",
             comments="", notes=""):
    return ["2026-11-01", DOMAIN, "words", slug, "url", "Jane", issue, langs,
            str(len(langs.split(","))), status, "", comments, notes]


@pytest.fixture
def run(monkeypatch):
    def _run(history_rows, current_rows):
        ws = FakeWorksheet([gs.HISTORY_HEADERS] + history_rows)
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: ws)
        monkeypatch.setattr(gs, "_auto_resize_columns", lambda ws: None)
        assert gs.update_history_tab(DOMAIN, SCAN, current_rows)
        return ws
    return _run


def col(name):
    return gs.HISTORY_HEADERS.index(name)


class TestNewRows:
    def test_new_row_gets_notes(self, run):
        ws = run([], [scan_row("p", notes="New post")])
        new = ws.rows[1]
        assert new[col("Status")] == "pending"
        assert new[col("Notes")] == "New post"
        assert len(new) == len(gs.HISTORY_HEADERS)

    def test_outdated_tracked_apart_from_missing(self, run):
        ws = run([hist_row("p", langs="fr")],
                 [scan_row("p", langs="fr"),
                  scan_row("p", config.ISSUE_OUTDATED, "de", notes="English updated …")])
        assert [r[col("Issue")] for r in ws.rows[1:]] == ["MISSING", "OUTDATED"]
        assert ws.rows[2][col("Notes")] == "English updated …"

    def test_row_without_notes_column_still_works(self, run):
        ws = run([], [scan_row("p")[:10]])          # scanner rows from before Notes
        assert ws.rows[1][col("Notes")] == ""


class TestExistingRows:
    def test_resolved_row_completed_and_notes_kept(self, run):
        ws = run([hist_row("p", config.ISSUE_OUTDATED, notes="English updated 2026-11-16")], [])
        r = ws.rows[1]
        assert r[col("Status")] == "completed"
        assert r[col("Completed Date")] == SCAN
        assert r[col("Notes")] == "English updated 2026-11-16"   # keeps why it was flagged

    def test_partial_row_updates_notes(self, run):
        ws = run([hist_row("p", langs="de, fr", notes="New post")],
                 [scan_row("p", langs="fr", notes="1 of 21 languages missing")])
        r = ws.rows[1]
        assert r[col("Status")] == "partial"
        assert r[col("Target Translations")] == "fr"
        assert r[col("Notes")] == "1 of 21 languages missing"

    def test_newer_reason_refreshes_notes_on_unchanged_row(self, run):
        ws = run([hist_row("p", config.ISSUE_OUTDATED, "de", notes="English updated 2026-11-01")],
                 [scan_row("p", config.ISSUE_OUTDATED, "de", notes="English updated 2026-11-16")])
        r = ws.rows[1]
        assert r[col("Status")] == "pending"
        assert r[col("Notes")] == "English updated 2026-11-16"

    def test_unchanged_row_and_reason_writes_nothing(self, run):
        ws = run([hist_row("p", notes="New post")], [scan_row("p", notes="New post")])
        assert ws.calls == []

    def test_comments_are_never_rewritten(self, run):
        # Comments start with "- " — written USER_ENTERED they'd turn into formulas
        ws = run([hist_row("p", langs="de, fr", comments="- Date: D\n- ✅ Translated 1/2")],
                 [scan_row("p", langs="fr", notes="x")])
        assert ws.rows[1][col("Comments")] == "- Date: D\n- ✅ Translated 1/2"
        # Only A..K (Scan Date..Completed Date) and M (Notes) are written; L is Comments
        assert sorted(rng for _, rng in ws.calls) == ["A2:K2", "M2"]

    def test_notes_written_raw(self, run):
        ws = run([hist_row("p", notes="old")], [scan_row("p", notes="- starts with a dash")])
        assert ("RAW", "M2") in ws.calls
        assert ws.rows[1][col("Notes")] == "- starts with a dash"

    def test_notes_column_found_by_header(self, monkeypatch):
        # A tab with an extra hand-added column before Notes
        header = gs.HISTORY_HEADERS[:-1] + ["Owner", "Notes"]
        ws = FakeWorksheet([header, hist_row("p", notes="")[:-1] + ["Ali", "old"]])
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: ws)
        monkeypatch.setattr(gs, "_auto_resize_columns", lambda ws: None)
        gs.update_history_tab(DOMAIN, SCAN, [scan_row("p", notes="new")])
        assert ws.rows[1][header.index("Owner")] == "Ali"
        assert ws.rows[1][header.index("Notes")] == "new"
