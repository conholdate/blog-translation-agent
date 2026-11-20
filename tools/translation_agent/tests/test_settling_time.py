"""
Tests for the settling time: a post is translated only once its English
index.md has gone config.TRANSLATION_SETTLE_HOURS (72 h) without a commit —
new (MISSING) and updated (OUTDATED) posts alike — so errors in the English
article can be fixed before they reach every language.

- the scanner writes 'Ready After' (last English commit + 72 h) and a
  '⏳ Waiting until …' line in Notes while the post is too fresh;
- each scan refreshes Ready After, so a new English edit restarts the wait;
- Step 2 skips rows until Ready After, except Urgent and ISSUE rows; a blank
  Ready After (no git history, manual row, older tab) means ready.
"""

from datetime import datetime, timezone

import config
import scan_queue as q
from scan_helpers import waiting_note
from translator import is_settled_row, split_settled

M, O, I = config.ISSUE_MISSING, config.ISSUE_OUTDATED, config.ISSUE_ISSUE
DOMAIN = "blog.aspose.com"
SCAN = "2026-11-20T00:00:00+00:00"

# 2026-11-19 14:05:00 UTC
EDIT_TS = int(datetime(2026, 11, 19, 14, 5, tzinfo=timezone.utc).timestamp())
READY = "2026-11-22 14:05 UTC"
BEFORE = datetime(2026, 11, 22, 14, 4, tzinfo=timezone.utc)
AFTER = datetime(2026, 11, 22, 14, 5, tzinfo=timezone.utc)


def test_default_is_72_hours():
    assert config.TRANSLATION_SETTLE_HOURS == 72
    assert config.KEY_READY_AFTER in config.HEADERS_QUEUE


class TestReadyAfter:
    def test_last_commit_plus_72_hours(self):
        assert q.ready_after(EDIT_TS) == READY

    def test_custom_hours(self):
        assert q.ready_after(EDIT_TS, hours=24) == "2026-11-20 14:05 UTC"

    def test_no_git_history_gives_blank(self):
        assert q.ready_after(0) == "" and q.ready_after(None) == ""

    def test_parse_round_trip_and_iso(self):
        assert q.parse_ready_after(READY) == datetime(2026, 11, 22, 14, 5, tzinfo=timezone.utc)
        assert q.parse_ready_after("2026-11-22T14:05") == datetime(2026, 11, 22, 14, 5, tzinfo=timezone.utc)
        assert q.parse_ready_after("2026-11-22") == datetime(2026, 11, 22, tzinfo=timezone.utc)

    def test_parse_blank_or_garbage_is_none(self):
        assert q.parse_ready_after("") is None
        assert q.parse_ready_after("soon") is None


class TestIsSettled:
    def row(self, issue=M, ready=READY, priority=""):
        return {config.KEY_ISSUE: issue, config.KEY_READY_AFTER: ready, config.KEY_PRIORITY: priority}

    def test_waits_until_ready_after(self):
        assert not q.is_settled(self.row(), BEFORE)
        assert q.is_settled(self.row(), AFTER)

    def test_same_rule_for_missing_and_outdated(self):
        assert not q.is_settled(self.row(O), BEFORE)
        assert q.is_settled(self.row(O), AFTER)

    def test_urgent_never_waits(self):
        assert q.is_settled(self.row(priority="Urgent"), BEFORE)
        assert q.is_settled(self.row(priority="urgent"), BEFORE)

    def test_high_priority_still_waits(self):
        assert not q.is_settled(self.row(priority="High"), BEFORE)

    def test_issue_rows_never_wait(self):
        assert q.is_settled(self.row(I), BEFORE)

    def test_blank_or_unreadable_ready_after_means_ready(self):
        assert q.is_settled(self.row(ready=""), BEFORE)
        assert q.is_settled(self.row(ready="n/a"), BEFORE)


class TestWaitingNote:
    def test_note_while_waiting(self):
        now = int(BEFORE.timestamp())
        assert waiting_note(EDIT_TS, 72, now) == \
            "⏳ Waiting until 2026-11-22 14:05 UTC (72 h after the last English edit)"

    def test_no_note_once_settled_or_without_history(self):
        assert waiting_note(EDIT_TS, 72, int(AFTER.timestamp())) == ""
        assert waiting_note(0, 72, int(BEFORE.timestamp())) == ""


# ---------------------------------------------------------------------------
# reconcile(): the scan writes and refreshes Ready After
# ---------------------------------------------------------------------------

def finding(slug, issue=M, langs="de, fr", ready=READY):
    return {"Domain": DOMAIN, "Product": "words", "Blog Post Directory": slug,
            "Blog Post URL": f"{DOMAIN}/words/{slug}/", "Author": "Jane", "Issue": issue,
            "Count": str(len(q.split_langs(langs))), "Target Translations": langs,
            "Action": config.ISSUE_ACTIONS[issue], "Notes": "", "Ready After": ready}


def qrow(slug, issue=M, langs="de, fr", **extra):
    row = {"Scan Date": "2026-11-10T00:00:00+00:00", "Missing Since": "2026-11-01", "Days Missing": "9",
           "Priority": config.DEFAULT_PRIORITY.get(issue, ""), "Domain": DOMAIN, "Product": "words",
           "Blog Post Directory": slug, "Blog Post URL": "", "Author": "Jane", "Issue": issue,
           "Count": str(len(q.split_langs(langs))), "Target Translations": langs,
           "Action": config.ISSUE_ACTIONS.get(issue, ""), "Status": "", "Source": "Scanner",
           "Notes": "", "Comments": "", "Ready After": ""}
    row.update(extra)
    return row


class TestReconcile:
    def test_new_row_gets_ready_after(self):
        (row,), _, _ = q.reconcile([], [finding("a")], SCAN)
        assert row["Ready After"] == READY

    def test_new_english_edit_restarts_the_wait(self):
        (row,), _, _ = q.reconcile([qrow("a", **{"Ready After": "2026-11-15 09:00 UTC"})],
                                   [finding("a", ready=READY)], SCAN)
        assert row["Ready After"] == READY

    def test_held_row_is_refreshed_too(self):
        (row,), _, _ = q.reconcile([qrow("a", Status="hold")], [finding("a")], SCAN)
        assert row["Ready After"] == READY and row["Status"] == "hold"

    def test_issue_rows_keep_their_blank_ready_after(self):
        (row,), _, _ = q.reconcile([qrow("a", I, Source="Manual")], [], SCAN)
        assert row["Ready After"] == ""

    def test_old_tab_without_the_column_gets_it(self):
        old = qrow("a")
        del old["Ready After"]
        (row,), _, _ = q.reconcile([old], [finding("a")], SCAN)
        assert row["Ready After"] == READY


# ---------------------------------------------------------------------------
# Step 2: rows still settling are held back (before the budget)
# ---------------------------------------------------------------------------

def step2_row(slug, issue=M, priority="", ready=READY):
    return [DOMAIN, "words", slug, "/words/x/", "Jane", issue, "2", "de, fr",
            config.ISSUE_ACTIONS[issue], "", priority, ready]


class TestStep2:
    def test_split_settled(self):
        rows = [step2_row("fresh"), step2_row("settled", ready="2026-11-01 00:00 UTC"),
                step2_row("urgent", priority="Urgent"), step2_row("issue", I),
                step2_row("outdated", O), step2_row("no-history", ready="")]
        ready, waiting = split_settled(rows, BEFORE)
        assert [r[2] for r in ready] == ["settled", "urgent", "issue", "no-history"]
        assert [r[2] for r in waiting] == ["fresh", "outdated"]

    def test_everything_ready_once_the_time_has_passed(self):
        ready, waiting = split_settled([step2_row("a"), step2_row("b", O)], AFTER)
        assert len(ready) == 2 and waiting == []

    def test_short_rows_without_the_column_are_ready(self):
        assert is_settled_row([DOMAIN, "words", "a", "", "Jane", M, "1", "de"], BEFORE)
        assert is_settled_row(step2_row("a")[:11], BEFORE)
