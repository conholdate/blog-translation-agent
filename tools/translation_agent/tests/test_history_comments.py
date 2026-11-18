"""
Tests for the per-post comment: build_history_comment() formatting, and
append_queue_comment(s) writing it to the post's open queue rows (Comments
column of the domain tab) against a fake worksheet.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from gspread.utils import a1_to_rowcol

import config
import io_google_spreadsheet as gs
from fake_sheet import FakeWorksheet
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
# append_queue_comments — comments go to the post's open queue rows
# ============================================================================

def _queue_row(slug, status="", comment="", langs="de", issue="MISSING"):
    row = {h: "" for h in config.HEADERS_QUEUE}
    row.update({"Domain": "blog.aspose.com", "Product": "medical", "Blog Post Directory": slug,
                "Issue": issue, "Target Translations": langs, "Status": status, "Comments": comment})
    return [row[h] for h in config.HEADERS_QUEUE]


C_COMMENTS = config.HEADERS_QUEUE.index("Comments") + 1      # 1-based sheet column


def written(ws):
    """(sheet row, value) of every Comments cell written."""
    out = []
    for method, rng, opt in ws.calls:
        if method == "batch_update":
            assert opt == "RAW"            # comments start with "- ": never a formula
            r, c = a1_to_rowcol(rng)
            assert c == C_COMMENTS
            out.append((r, ws.rows[r - 1][c - 1]))
    return out


class TestAppendQueueComment:
    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet([
            config.HEADERS_QUEUE,
            _queue_row("held-post", status="hold"),
            _queue_row("my-post"),
            _queue_row("other-post", comment="old"),
        ])
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        return ws

    def test_writes_comment_to_open_row(self, ws):
        assert gs.append_queue_comment("blog.aspose.com", "my-post", "C1") is True
        assert written(ws) == [(3, "C1")]

    def test_appends_below_existing_comment_with_blank_line(self, ws):
        gs.append_queue_comment("blog.aspose.com", "other-post", "new")
        assert written(ws) == [(4, "old\n\nnew")]

    def test_ignores_rows_that_are_not_open(self, ws):
        assert gs.append_queue_comment("blog.aspose.com", "held-post", "C") is False
        assert written(ws) == []

    def test_unknown_post_returns_false(self, ws):
        assert gs.append_queue_comment("blog.aspose.com", "nope", "C") is False

    def test_rows_found_by_key_after_the_tab_changed(self, ws):
        ws.rows.insert(1, _queue_row("inserted-later"))      # someone added a row mid-run
        gs.append_queue_comment("blog.aspose.com", "my-post", "C1")
        assert written(ws) == [(4, "C1")]

    def test_adds_comments_column_to_old_tab(self, monkeypatch):
        header = [h for h in config.HEADERS_QUEUE if h != "Comments"]
        row = dict(zip(config.HEADERS_QUEUE, _queue_row("my-post")))
        ws = FakeWorksheet([header, [row[h] for h in header]])
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        assert gs.append_queue_comment("blog.aspose.com", "my-post", "C1") is True
        assert ws.rows[0][-1] == "Comments" and ws.rows[1][len(header)] == "C1"

    def test_never_raises(self, monkeypatch):
        def boom(domain):
            raise RuntimeError("sheet down")
        monkeypatch.setattr(gs, "get_scan_worksheet", boom)
        assert gs.append_queue_comment("blog.aspose.com", "my-post", "C") is False


class TestSplitQueueRows:
    """A post with several open queue rows, each tracking its own languages."""

    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet([
            config.HEADERS_QUEUE,
            _queue_row("using-converter", langs="ar, cs"),                  # row 2
            _queue_row("using-converter", langs="de"),                      # row 3
            _queue_row("using-converter", langs="es, fa", issue="OUTDATED"),  # row 4
            _queue_row("using-converter", langs="fr, he, id", issue="ISSUE"),  # row 5
            _queue_row("other-post", langs="de"),                           # row 6
        ])
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        return ws

    @staticmethod
    def comment_for(row_langs):
        return "ALL" if row_langs is None else ",".join(row_langs)

    def test_each_matching_row_gets_its_own_languages_whatever_the_issue(self, ws):
        gs.append_queue_comments("blog.aspose.com", "using-converter", self.comment_for,
                                 run_langs=["de", "es", "fa"])
        assert written(ws) == [(3, "de"), (4, "es,fa")]

    def test_partial_overlap_gets_only_shared_languages(self, ws):
        gs.append_queue_comments("blog.aspose.com", "using-converter", self.comment_for,
                                 run_langs=["cs", "fr"])
        assert written(ws) == [(2, "cs"), (5, "fr")]

    def test_no_overlap_falls_back_to_last_open_row(self, ws):
        gs.append_queue_comments("blog.aspose.com", "using-converter", self.comment_for,
                                 run_langs=["ja"])
        assert written(ws) == [(5, "ALL")]

    def test_whole_post_comment_goes_to_every_open_row(self, ws):
        gs.append_queue_comment("blog.aspose.com", "using-converter", "❌ Failed")
        assert [r for r, _ in written(ws)] == [2, 3, 4, 5]
        assert {v for _, v in written(ws)} == {"❌ Failed"}


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


class TestClosingLanguages:
    """append_queue_comments(done_langs=…): Step 2 removes what it translated and closes empty rows."""

    @pytest.fixture
    def ws(self, monkeypatch):
        ws = FakeWorksheet([
            config.HEADERS_QUEUE,
            _queue_row("post", langs="de, fr"),                       # row 2 MISSING
            _queue_row("post", langs="fr", issue="OUTDATED"),         # row 3
            _queue_row("post", langs="fr, it", issue="ISSUE"),        # row 4
            _queue_row("other", langs="fr"),                          # row 5
        ])
        monkeypatch.setattr(gs, "get_scan_worksheet", lambda domain: ws)
        self.history = []
        monkeypatch.setattr(gs, "append_history_rows",
                            lambda domain, rows: self.history.extend(rows) or True)
        return ws

    def rows(self, ws):
        return [(r[2], r[5], r[7]) for r in [[row[config.HEADERS_QUEUE.index(h)] for h in
                ("Domain", "Product", "Blog Post Directory", "Blog Post URL", "Author", "Issue",
                 "Count", "Target Translations")] for row in ws.get_all_values()[1:]]]

    def test_one_translation_settles_every_row_tracking_the_language(self, ws):
        gs.append_queue_comments("blog.aspose.com", "post", lambda langs: "ok",
                                 run_langs=["fr"], done_langs=["fr"])
        assert self.rows(ws) == [("post", "MISSING", "de"), ("post", "ISSUE", "it"), ("other", "MISSING", "fr")]
        (closed,) = self.history
        assert closed["Issue"] == "OUTDATED" and closed["Status"] == "completed"
        assert closed["Comments"] == "ok" and closed["Completed Date"]

    def test_shrunk_rows_become_partial(self, ws):
        gs.append_queue_comments("blog.aspose.com", "post", lambda langs: "ok",
                                 run_langs=["de"], done_langs=["de"])
        status = config.HEADERS_QUEUE.index("Status")
        assert ws.rows[1][status] == "partial"
        assert ws.rows[1][config.HEADERS_QUEUE.index("Count")] == "1"

    def test_closed_rows_are_deleted_bottom_up(self, ws):
        gs.append_queue_comments("blog.aspose.com", "post", lambda langs: "ok",
                                 run_langs=["de", "fr", "it"], done_langs=["de", "fr", "it"])
        starts = [r["deleteDimension"]["range"]["startIndex"] for r in ws.spreadsheet.requests]
        assert starts == sorted(starts, reverse=True) == [3, 2, 1]
        assert self.rows(ws) == [("other", "MISSING", "fr")]
        assert len(self.history) == 3

    def test_failed_languages_stay_open(self, ws):
        gs.append_queue_comments("blog.aspose.com", "post", lambda langs: "partial",
                                 run_langs=["fr", "it"], done_langs=["fr"])
        assert ("post", "ISSUE", "it") in self.rows(ws)

    def test_comment_only_when_nothing_done(self, ws):
        gs.append_queue_comments("blog.aspose.com", "post", lambda langs: "❌",
                                 run_langs=["fr"], done_langs=[])
        assert len(self.rows(ws)) == 4 and self.history == []
