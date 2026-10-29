"""
Tests for the per-post history comment: build_history_comment() formatting and
append_history_comment() / _ensure_history_columns() against a fake worksheet.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import io_google_spreadsheet as gs
from translator import build_history_comment

LANGS = ["ar", "cs", "de", "es", "fa", "fr", "he", "id", "it", "ja", "ko",
         "pl", "pt", "ru", "sv", "th", "tr", "uk", "vi", "zh", "zh-hant"]


# ============================================================================
# build_history_comment
# ============================================================================

class TestBuildHistoryComment:
    def test_partial_with_failed_and_kept_links(self):
        failed = ["fa", "he", "uk"]
        ok = [l for l in LANGS if l not in failed]
        comment = build_history_comment(
            total=21, succeeded=ok, failed=failed, lang_order=LANGS,
            kept_english={"/total/foo/": set(LANGS)}, date="2026-10-29")
        assert comment == (
            "- Date: 2026-10-29\n"
            "- ⚠️ Partial 18/21\n"
            "- Failed: fa, he, uk\n"
            "- EN links kept (translated URL would be 404): /total/foo/ [ar, cs, de +18]"
        )

    def test_all_translated(self):
        assert build_history_comment(total=2, succeeded=["de", "ar"], date="D") == "- Date: D\n- ✅ Translated 2/2"

    def test_already_existing_count_as_done(self):
        comment = build_history_comment(total=2, succeeded=["de"], skipped=["ar"], date="D")
        assert comment == "- Date: D\n- ✅ Translated 2/2\n- Already existed: ar"

    def test_all_failed(self):
        comment = build_history_comment(total=2, failed=["de", "ar"], date="D")
        assert comment == "- Date: D\n- ❌ Failed 0/2\n- Failed: de, ar"

    def test_post_error_is_single_line_and_truncated(self):
        comment = build_history_comment(error="ValueError: bad\nframe " + "x" * 500, date="D")
        date_line, error_line = comment.split("\n")
        assert date_line == "- Date: D"
        assert error_line.startswith("- ❌ Failed: ValueError: bad frame x")
        assert len(error_line) <= len("- ❌ Failed: ") + 200

    def test_draft(self):
        assert build_history_comment(draft=True, date="D") == "- Date: D\n- ⏭️ Skipped: draft"

    def test_multiple_kept_links_sorted_and_short_lang_lists(self):
        comment = build_history_comment(
            total=2, succeeded=["de", "fr"], lang_order=["de", "fr"], date="D",
            kept_english={"/b/": {"fr"}, "/a/": {"fr", "de"}})
        assert comment.endswith("would be 404): /a/ [de, fr]; /b/ [fr]")


# ============================================================================
# Fake gspread worksheet
# ============================================================================

class FakeWorksheet:
    def __init__(self, rows, col_count=None):
        self.rows = [list(r) for r in rows]
        self.col_count = col_count or max(len(r) for r in rows)
        self.updated_cells = []

    def row_values(self, i):
        return list(self.rows[i - 1])

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def add_cols(self, n):
        self.col_count += n

    def update(self, values, range_name, value_input_option=None):
        col = ord(range_name.rstrip("0123456789")[-1]) - ord("A")
        for j, v in enumerate(values[0]):
            row = self.rows[0]
            row += [""] * (col + j + 1 - len(row))
            row[col + j] = v

    def update_cell(self, row, col, value):
        self.updated_cells.append((row, col, value))
        r = self.rows[row - 1]
        r += [""] * (col - len(r))
        r[col - 1] = value

    def batch_update(self, updates, value_input_option=None):
        from gspread.utils import a1_to_rowcol
        for u in updates:
            row, col = a1_to_rowcol(u["range"])
            self.update_cell(row, col, u["values"][0][0])


OLD_HEADER = gs.HISTORY_HEADERS[:-1]      # tab created before 'Comments' existed


def _hist_row(slug, status="pending", comment=None, langs="de"):
    row = ["2026-10-21", "blog.aspose.com", "medical", slug, "url", "A", "MISSING", langs,
           str(len(langs.split(","))), status, ""]
    return row + ([comment] if comment is not None else [])


class TestEnsureHistoryColumns:
    def test_adds_comments_column_and_widens_grid(self):
        ws = FakeWorksheet([OLD_HEADER], col_count=11)
        gs._ensure_history_columns(ws)
        assert ws.rows[0][-1] == "Comments"
        assert ws.col_count == 12

    def test_noop_when_present(self):
        ws = FakeWorksheet([gs.HISTORY_HEADERS])
        gs._ensure_history_columns(ws)
        assert ws.rows[0] == gs.HISTORY_HEADERS


class TestAppendHistoryComment:
    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet([
            gs.HISTORY_HEADERS,
            _hist_row("done-post", status="completed"),
            _hist_row("my-post"),
            _hist_row("other-post", comment="old"),
        ])
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: ws)
        return ws

    def test_writes_comment_to_open_row(self, ws):
        assert gs.append_history_comment("blog.aspose.com", "my-post", "C1") is True
        assert ws.updated_cells == [(3, 12, "C1")]

    def test_appends_below_existing_comment_with_blank_line(self, ws):
        gs.append_history_comment("blog.aspose.com", "other-post", "new")
        assert ws.updated_cells == [(4, 12, "old\n\nnew")]

    def test_ignores_completed_rows(self, ws):
        assert gs.append_history_comment("blog.aspose.com", "done-post", "C") is False
        assert ws.updated_cells == []

    def test_unknown_post_returns_false(self, ws):
        assert gs.append_history_comment("blog.aspose.com", "nope", "C") is False

    def test_never_raises(self, monkeypatch):
        def boom():
            raise RuntimeError("sheet down")
        monkeypatch.setattr(gs, "_get_history_worksheet", boom)
        assert gs.append_history_comment("blog.aspose.com", "my-post", "C") is False


class TestSplitHistoryRows:
    """A post with several open history rows, each tracking its own languages."""

    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet([
            gs.HISTORY_HEADERS,
            _hist_row("using-converter", langs="ar, cs"),          # row 2
            _hist_row("using-converter", langs="de"),              # row 3
            _hist_row("using-converter", langs="es, fa"),          # row 4
            _hist_row("using-converter", langs="fr, he, id"),      # row 5
            _hist_row("other-post", langs="de"),                   # row 6
        ])
        monkeypatch.setattr(gs, "_get_history_worksheet", lambda: ws)
        return ws

    @staticmethod
    def comment_for(row_langs):
        return "ALL" if row_langs is None else ",".join(row_langs)

    def test_each_matching_row_gets_its_own_languages(self, ws):
        gs.append_history_comments("blog.aspose.com", "using-converter", self.comment_for,
                                   run_langs=["de", "es", "fa"])
        assert ws.updated_cells == [(3, 12, "de"), (4, 12, "es,fa")]

    def test_partial_overlap_gets_only_shared_languages(self, ws):
        gs.append_history_comments("blog.aspose.com", "using-converter", self.comment_for,
                                   run_langs=["cs", "fr"])
        assert ws.updated_cells == [(2, 12, "cs"), (5, 12, "fr")]

    def test_no_overlap_falls_back_to_last_open_row(self, ws):
        gs.append_history_comments("blog.aspose.com", "using-converter", self.comment_for,
                                   run_langs=["ja"])
        assert ws.updated_cells == [(5, 12, "ALL")]

    def test_whole_post_comment_goes_to_every_open_row(self, ws):
        gs.append_history_comment("blog.aspose.com", "using-converter", "❌ Failed")
        assert [r for r, _, _ in ws.updated_cells] == [2, 3, 4, 5]
        assert {v for _, _, v in ws.updated_cells} == {"❌ Failed"}


class TestPerRowCommentContent:
    """The translator's per-row comment: only the row's languages are reported."""

    def test_row_subset_comment(self):
        langs = ["de", "es", "fa"]
        succeeded, failed = ["de", "es"], ["fa"]
        kept = {"/total/foo/": {"de", "fa"}}

        def comment_for(row_langs):
            subset = set(row_langs) if row_langs is not None else set(langs)
            return build_history_comment(
                total=len(subset),
                succeeded=[l for l in succeeded if l in subset],
                failed=[l for l in failed if l in subset],
                kept_english={p: ls & subset for p, ls in kept.items() if ls & subset},
                lang_order=langs, date="D")

        assert comment_for(["de"]) == (
            "- Date: D\n- ✅ Translated 1/1\n"
            "- EN links kept (translated URL would be 404): /total/foo/ [de]")
        assert comment_for(["es", "fa"]) == (
            "- Date: D\n- ⚠️ Partial 1/2\n- Failed: fa\n"
            "- EN links kept (translated URL would be 404): /total/foo/ [fa]")
