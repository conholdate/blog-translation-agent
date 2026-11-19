"""
Tests for resort_queue.py: only OUTDATED rows move (newest post first, among
their own places), people's cells are untouched, dry run changes nothing, and
a changed tab is backed up before it is written.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import io_google_spreadsheet as gs
import resort_queue as resort
from fake_sheet import FakeWorksheet

M, O, I = config.ISSUE_MISSING, config.ISSUE_OUTDATED, config.ISSUE_ISSUE
HEADER = config.HEADERS_QUEUE + ["My Column"]


def row(slug, issue, comment=""):
    r = dict.fromkeys(HEADER, "")
    r.update({"Domain": "blog.aspose.com", "Blog Post Directory": slug, "Issue": issue,
              "Comments": comment, "My Column": f"mine-{slug}"})
    return [r[h] for h in HEADER]


def slugs(values):
    i = HEADER.index("Blog Post Directory")
    return [r[i] for r in values[1:]]


class FakeSheet:
    def __init__(self, tabs):
        self.tabs = tabs
        self.duplicated = []
        for i, ws in enumerate(tabs):
            ws.id = i

    def worksheets(self):
        return list(self.tabs)

    def duplicate_sheet(self, sheet_id, new_sheet_name=None):
        self.duplicated.append(new_sheet_name)


def make_sheet():
    aspose = FakeWorksheet([HEADER,
                            row("2026-11-18-m", M),
                            row("2022-09-22-old", O, "- run 1"),
                            row("2021-01-01-i", I),
                            row("2026-09-30-new", O),
                            row("undated", O),
                            row("2024-05-05-mid", O)], title="blog.aspose.com")
    cloud = FakeWorksheet([HEADER, row("2026-01-01-a", O), row("2020-01-01-b", O)], title="blog.aspose.cloud")
    sorted_tab = FakeWorksheet([HEADER, row("2026-01-01-a", O)], title="blog.conholdate.com")
    return FakeSheet([aspose, cloud, sorted_tab])


class TestOutdatedNewestFirst:
    def test_only_outdated_rows_move_among_their_places(self):
        rows = [{"Issue": M, "Blog Post Directory": "2019-01-01-m"},
                {"Issue": O, "Blog Post Directory": "2022-01-01-a"},
                {"Issue": I, "Blog Post Directory": "2018-01-01-i"},
                {"Issue": O, "Blog Post Directory": "2026-01-01-b"}]
        out, moved = resort.outdated_newest_first(rows)
        assert [r["Blog Post Directory"] for r in out] == ["2019-01-01-m", "2026-01-01-b", "2018-01-01-i", "2022-01-01-a"]
        assert moved == 2

    def test_already_sorted_moves_nothing(self):
        rows = [{"Issue": O, "Blog Post Directory": "2026-01-01-b"}, {"Issue": O, "Blog Post Directory": "2022-01-01-a"}]
        assert resort.outdated_newest_first(rows)[1] == 0


class TestMain:
    def test_dry_run_changes_nothing(self, monkeypatch, capsys):
        sheet = make_sheet()
        before = [ws.get_all_values() for ws in sheet.tabs]
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: sheet)
        assert resort.main([]) == 0
        assert [ws.get_all_values() for ws in sheet.tabs] == before and sheet.duplicated == []
        assert "DRY RUN" in capsys.readouterr().out

    def test_apply_backs_up_and_resorts_keeping_cells(self, monkeypatch):
        sheet = make_sheet()
        aspose, cloud, sorted_tab = sheet.tabs
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: sheet)
        assert resort.main(["--apply"]) == 0

        assert slugs(aspose.get_all_values()) == ["2026-11-18-m", "2026-09-30-new", "2021-01-01-i",
                                                  "2024-05-05-mid", "2022-09-22-old", "undated"]
        assert slugs(cloud.get_all_values()) == ["2026-01-01-a", "2020-01-01-b"]       # already in order
        old = next(r for r in aspose.get_all_values() if "2022-09-22-old" in r)
        assert old[HEADER.index("Comments")] == "- run 1" and old[-1] == "mine-2022-09-22-old"
        assert aspose.get_all_values()[0] == HEADER
        assert len(sheet.duplicated) == 1 and sheet.duplicated[0].endswith("-blog.aspose.com")

    def test_one_domain(self, monkeypatch):
        sheet = make_sheet()
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: sheet)
        assert resort.main(["--domain", "blog.aspose.cloud", "--apply"]) == 0
        assert slugs(sheet.tabs[0].get_all_values())[1] == "2022-09-22-old"       # aspose.com untouched
        assert sheet.duplicated == []

    def test_no_sheet_access_fails(self, monkeypatch):
        monkeypatch.setattr(gs, "_open_scan_sheet", lambda: None)
        assert resort.main([]) == 1
