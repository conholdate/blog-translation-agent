"""
Tests for scan_queue.reconcile() — how a scan updates the persistent queue
(domain tab): languages fixed since the last scan are removed, empty rows are
closed (for history), new findings are added at the bottom, and everything
people set (row splits, Priority, Status, Comments, manual rows) is kept.
"""

import config
import scan_queue as q

DOMAIN = "blog.aspose.com"
SCAN = "2026-11-18T00:00:00+00:00"
M, O, I = config.ISSUE_MISSING, config.ISSUE_OUTDATED, config.ISSUE_ISSUE


def finding(slug, issue=M, langs="de, fr", notes="", product="words"):
    return {"Domain": DOMAIN, "Product": product, "Blog Post Directory": slug,
            "Blog Post URL": f"{DOMAIN}/{product}/{slug}/", "Author": "Jane",
            "Issue": issue, "Count": str(len(q.split_langs(langs))), "Target Translations": langs,
            "Action": config.ISSUE_ACTIONS[issue], "Notes": notes}


def qrow(slug, issue=M, langs="de, fr", product="words", **extra):
    row = {"Scan Date": "2026-11-10T00:00:00+00:00", "Missing Since": "2026-11-01", "Days Missing": "9",
           "Priority": config.DEFAULT_PRIORITY.get(issue, ""), "Domain": DOMAIN, "Product": product,
           "Blog Post Directory": slug, "Blog Post URL": f"{DOMAIN}/{product}/{slug}/", "Author": "Jane",
           "Issue": issue, "Count": str(len(q.split_langs(langs))), "Target Translations": langs,
           "Action": config.ISSUE_ACTIONS.get(issue, ""), "Status": "", "Source": "Scanner",
           "Notes": "", "Comments": ""}
    row.update(extra)
    return row


def run(queue, findings):
    return q.reconcile(queue, findings, SCAN)


def slugs(rows):
    return [(r["Blog Post Directory"], r["Issue"], r["Target Translations"]) for r in rows]


class TestEmptyQueue:
    def test_scan_on_empty_queue_rebuilds_it_in_finding_order(self):
        out, closed, added = run([], [finding("a"), finding("b", O, "it", notes="English updated")])
        assert slugs(out) == [("a", M, "de, fr"), ("b", O, "it")]
        assert closed == [] and added == out

    def test_new_row_defaults(self):
        (row,), _, _ = run([], [finding("a", O, "it", notes="why")])
        assert row["Priority"] == config.PRIORITY_LOW
        assert row["Source"] == config.SOURCE_SCANNER
        assert row["Missing Since"] == "2026-11-18" and row["Days Missing"] == "0"
        assert row["Scan Date"] == SCAN
        assert row["Action"] == config.ACTION_RETRANSLATE
        assert row["Notes"] == "why" and row["Count"] == "1"

    def test_missing_rows_are_high_priority(self):
        (row,), _, _ = run([], [finding("a")])
        assert row["Priority"] == config.PRIORITY_HIGH


class TestExistingRows:
    def test_unchanged_row_keeps_missing_since_and_counts_days(self):
        (row,), closed, added = run([qrow("a")], [finding("a", notes="new reason")])
        assert row["Missing Since"] == "2026-11-01" and row["Days Missing"] == "17"
        assert row["Scan Date"] == SCAN
        assert row["Notes"] == "new reason"
        assert closed == [] and added == []

    def test_fixed_languages_are_removed_and_row_marked_partial(self):
        (row,), closed, _ = run([qrow("a", langs="de, fr, it")], [finding("a", langs="fr")])
        assert row["Target Translations"] == "fr" and row["Count"] == "1"
        assert row["Status"] == "partial"
        assert closed == []

    def test_row_with_nothing_left_is_closed_for_history(self):
        out, (done,), _ = run([qrow("a", Comments="- Date: x")], [])
        assert out == []
        assert done["Status"] == config.STATUS_COMPLETED
        assert done["Completed Date"] == SCAN
        assert done["Target Translations"] == "de, fr"
        assert done["Comments"] == "- Date: x"

    def test_people_set_values_survive(self):
        row = qrow("a", Priority="Urgent", Comments="- run 1", Source="Manual")
        row["My Column"] = "keep me"
        (out,), _, _ = run([row], [finding("a")])
        assert out["Priority"] == "Urgent" and out["Comments"] == "- run 1"
        assert out["Source"] == "Manual" and out["My Column"] == "keep me"

    def test_url_and_author_refreshed_from_scan(self):
        f = finding("a")
        f["Author"] = "New Author"
        (row,), _, _ = run([qrow("a")], [f])
        assert row["Author"] == "New Author"

    def test_sheet_order_is_kept_and_new_rows_go_last(self):
        out, _, _ = run([qrow("b"), qrow("a")], [finding("a"), finding("c"), finding("b")])
        assert [r["Blog Post Directory"] for r in out] == ["b", "a", "c"]

    def test_blank_and_placeholder_rows_dropped(self):
        placeholder = {"Domain": "", "Product": "!!! NO MISSING TRANSLATION FOUND !!!"}
        out, closed, _ = run([placeholder, qrow("a")], [finding("a")])
        assert slugs(out) == [("a", M, "de, fr")] and closed == []


class TestSplitRows:
    def test_split_rows_stay_split_and_shrink_independently(self):
        queue = [qrow("a", langs="ar, cs"), qrow("a", langs="de, fr")]
        out, closed, added = run(queue, [finding("a", langs="cs, de, fr")])
        assert slugs(out) == [("a", M, "cs"), ("a", M, "de, fr")]
        assert closed == [] and added == []

    def test_one_split_row_closes_the_other_stays(self):
        queue = [qrow("a", langs="ar, cs"), qrow("a", langs="de, fr")]
        out, closed, _ = run(queue, [finding("a", langs="de, fr")])
        assert slugs(out) == [("a", M, "de, fr")]
        assert slugs(closed) == [("a", M, "ar, cs")]

    def test_newly_flagged_language_gets_its_own_row(self):
        out, _, added = run([qrow("a", langs="de")], [finding("a", langs="de, it")])
        assert slugs(out) == [("a", M, "de"), ("a", M, "it")]
        assert slugs(added) == [("a", M, "it")]


class TestIssuesTrackedApart:
    def test_missing_and_outdated_of_one_post_are_separate_rows(self):
        out, _, _ = run([qrow("a", langs="fr")], [finding("a", langs="fr"), finding("a", O, "de")])
        assert slugs(out) == [("a", M, "fr"), ("a", O, "de")]

    def test_same_slug_in_another_product_is_another_post(self):
        out, closed, _ = run([qrow("a", product="pdf")], [finding("a", product="words")])
        assert [r["Product"] for r in out] == ["words"]
        assert [r["Product"] for r in closed] == ["pdf"]

    def test_issue_rows_are_left_alone_by_the_scan(self):
        row = qrow("a", I, "fr", Source="Manual", Notes="bad tables")
        (out,), closed, _ = run([row], [])
        assert out["Target Translations"] == "fr" and out["Notes"] == "bad tables"
        assert closed == []


class TestNotOpenRows:
    def test_held_row_is_kept_and_blocks_duplicates(self):
        row = qrow("a", Status="hold")
        out, closed, added = run([row], [finding("a")])
        assert slugs(out) == [("a", M, "de, fr")] and out[0]["Status"] == "hold"
        assert closed == [] and added == []

    def test_held_row_is_not_closed_when_resolved(self):
        out, closed, _ = run([qrow("a", Status="hold")], [])
        assert len(out) == 1 and closed == []


class TestManualRowsFilledIn:
    def test_blank_priority_source_action_and_since_are_filled(self):
        row = {"Domain": DOMAIN, "Product": "words", "Blog Post Directory": "a",
               "Issue": I, "Target Translations": "fr"}
        (out,), _, _ = run([row], [])
        assert out["Priority"] == config.PRIORITY_NORMAL
        assert out["Source"] == config.SOURCE_MANUAL
        assert out["Action"] == config.ACTION_RETRANSLATE
        assert out["Missing Since"] == "2026-11-18" and out["Days Missing"] == "0"


class TestHelpers:
    def test_priority_rank(self):
        assert q.priority_rank({"Priority": "Urgent", "Issue": O}) == 0
        assert q.priority_rank({"Priority": "", "Issue": M}) == 1
        assert q.priority_rank({"Priority": "bogus", "Issue": O}) == 3
        assert q.priority_rank({"Issue": I}) == 2

    def test_is_open(self):
        assert q.is_open({"Status": ""}) and q.is_open({"Status": "Partial"})
        assert not q.is_open({"Status": "invalid"}) and not q.is_open({"Status": "hold"})

    def test_values_round_trip_and_header_merge(self):
        header, rows = q.from_values([["Domain", "Mine"], ["d", "x", "extra"], ["e"]])
        assert rows == [{"Domain": "d", "Mine": "x"}, {"Domain": "e", "Mine": ""}]
        assert q.to_values(rows, ["Mine", "Domain"]) == [["x", "d"], ["", "e"]]
        assert q.merged_header(["Mine", "Domain"], ["Domain", "Issue"]) == ["Mine", "Domain", "Issue"]

    def test_post_date_from_folder_name(self):
        assert q.post_date("2026-11-18-convert-svg") == 20261118
        assert q.post_date(" 2022-09-22-x ") == 20220922
        assert q.post_date("convert-svg") == 0 and q.post_date("") == 0


class TestWorkOrder:
    """order_rows(): Priority, FIFO within it — OUTDATED newest post first."""

    @staticmethod
    def order(rows):
        out = q.order_rows(rows, rank=q.priority_rank,
                           is_outdated=lambda r: r["Issue"] == O, slug=lambda r: r["Blog Post Directory"])
        return [r["Blog Post Directory"] for r in out]

    def test_outdated_newest_post_first(self):
        rows = [qrow("2022-09-22-a", O), qrow("2026-11-01-b", O), qrow("2024-05-05-c", O)]
        assert self.order(rows) == ["2026-11-01-b", "2024-05-05-c", "2022-09-22-a"]

    def test_missing_and_issue_stay_first_in_first_out(self):
        rows = [qrow("2022-01-01-old", M), qrow("2026-01-01-new", M),
                qrow("2021-01-01-i1", I), qrow("2025-01-01-i2", I)]
        assert self.order(rows) == ["2022-01-01-old", "2026-01-01-new", "2021-01-01-i1", "2025-01-01-i2"]

    def test_undated_folders_last_and_ties_keep_sheet_order(self):
        rows = [qrow("undated", O), qrow("2026-01-01-x", O, langs="de"), qrow("2026-01-01-x", O, langs="fr")]
        out = q.order_rows(rows, rank=q.priority_rank, is_outdated=lambda r: r["Issue"] == O,
                           slug=lambda r: r["Blog Post Directory"])
        assert [(r["Blog Post Directory"], r["Target Translations"]) for r in out] == [
            ("2026-01-01-x", "de"), ("2026-01-01-x", "fr"), ("undated", "de, fr")]

    def test_priority_still_comes_first(self):
        rows = [qrow("2026-01-01-new", O), qrow("2020-01-01-old", O, Priority="Urgent"),
                qrow("2019-01-01-m", M)]
        assert self.order(rows) == ["2020-01-01-old", "2019-01-01-m", "2026-01-01-new"]

    def test_raised_outdated_row_keeps_its_place_among_missing(self):
        rows = [qrow("2019-01-01-m1", M), qrow("2020-01-01-o-old", O, Priority="High"),
                qrow("2021-01-01-m2", M), qrow("2026-01-01-o-new", O, Priority="High")]
        assert self.order(rows) == ["2019-01-01-m1", "2026-01-01-o-new", "2021-01-01-m2", "2020-01-01-o-old"]

    def test_days_between(self):
        assert q.days_between("", "2026-10-29") == ""
        assert q.days_between("2026-10-21", "2026-10-29T03:00:00+00:00") == "8"


class TestManualRowValidation:
    POSTS = {("words", "a"), ("words", "b")}
    LANGS = ["de", "fr", "it"]

    def run(self, queue):
        return q.reconcile(queue, [], SCAN, posts=self.POSTS, supported_langs=self.LANGS)

    def test_valid_issue_row_stays_open(self):
        (row,), _, _ = self.run([qrow("a", I, "fr", Notes="bad tables")])
        assert row["Status"] == "" and row["Notes"] == "bad tables" and row["Scan Date"] == SCAN

    def test_blank_languages_mean_all(self):
        (row,), _, _ = self.run([qrow("a", I, "")])
        assert row["Target Translations"] == "de, fr, it" and row["Count"] == "3"

    def test_unknown_post_is_invalid_and_keeps_the_persons_note(self):
        (row,), closed, _ = self.run([qrow("zzz", I, "fr", Notes="bad tables")])
        assert row["Status"] == "invalid" and closed == []
        first, second = row["Notes"].split("\n")
        assert first.startswith("⚠️ Invalid: post folder not found") and second == "bad tables"

    def test_unsupported_language_is_invalid(self):
        (row,), _, _ = self.run([qrow("a", I, "fr, xx")])
        assert row["Status"] == "invalid" and "unsupported language(s): xx" in row["Notes"]

    def test_unknown_issue_is_invalid(self):
        (row,), _, _ = self.run([qrow("a", "BROKEN", "fr")])
        assert row["Status"] == "invalid" and "unknown issue 'BROKEN'" in row["Notes"]

    def test_fixed_row_becomes_valid_again(self):
        bad = qrow("zzz", I, "fr", Status="invalid", Notes="⚠️ Invalid: post folder not found\nbad tables")
        bad["Blog Post Directory"] = "b"            # the person corrected the folder
        (row,), _, _ = self.run([bad])
        assert row["Status"] == "" and row["Notes"] == "bad tables"

    def test_held_issue_row_is_not_validated(self):
        (row,), _, _ = self.run([qrow("zzz", I, "fr", Status="hold")])
        assert row["Status"] == "hold"

    def test_without_post_list_nothing_is_validated(self):
        (row,), _, _ = q.reconcile([qrow("zzz", I, "fr")], [], SCAN)
        assert row["Status"] == ""

    def test_old_extra_rows_leave_the_queue(self):
        out, closed, _ = self.run([qrow("a", config.ISSUE_EXTRA, "tmp")])
        assert out == [] and closed == []
