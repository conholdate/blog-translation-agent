"""
Tests for OUTDATED / Retranslate rows in translator.py: they pass the row
filters, are queued by priority (MISSING High before OUTDATED Low by default),
overwrite existing translations and log their comment for their own languages.
"""

import pytest

import config
import translator
from translator import (TranslationOrchestrator, drop_existing_translations, filter_valid_rows,
                        is_outdated_row, queue_order)


def make_row(slug="my-post", issue=config.ISSUE_MISSING, langs="de, fr", product="email",
             status="", priority=None):
    row = ["blog.aspose.com", product, slug, "/email/my-post/", "Jane", issue,
           str(len(langs.split(","))), langs]
    if status or priority is not None:
        row += [config.ISSUE_ACTIONS.get(issue, ""), status, priority or ""]
    return row


M = config.ISSUE_MISSING
O = config.ISSUE_OUTDATED
E = config.ISSUE_EXTRA


class TestRowHelpers:
    def test_outdated_rows_pass_filter_valid_rows(self):
        rows = [make_row(issue=O), make_row(issue=M), make_row(issue=E)]
        assert [r[5] for r in filter_valid_rows(rows)] == [O, M]

    def test_is_outdated_row(self):
        assert is_outdated_row(make_row(issue=O))
        assert not is_outdated_row(make_row(issue=M))
        assert not is_outdated_row(["short"])

    def test_default_priority_puts_missing_first_keeping_order_within_each_group(self):
        rows = [make_row("o1", O), make_row("m1", M), make_row("o2", O), make_row("m2", M)]
        assert [r[2] for r in queue_order(rows)] == ["m1", "m2", "o1", "o2"]

    def test_priority_column_overrides_issue_default(self):
        rows = [make_row("m1", M, priority=config.PRIORITY_HIGH),
                make_row("o1", O, priority=config.PRIORITY_URGENT),
                make_row("m2", M, priority=config.PRIORITY_LOW),
                make_row("o2", O, priority="")]           # blank → OUTDATED default (Low)
        assert [r[2] for r in queue_order(rows)] == ["o1", "m1", "m2", "o2"]

    def test_priority_is_case_insensitive(self):
        rows = [make_row("m1", M), make_row("o1", O, priority="urgent")]
        assert [r[2] for r in queue_order(rows)] == ["o1", "m1"]

    def test_rows_that_are_not_open_are_skipped(self):
        rows = [make_row("a", M, status="invalid"), make_row("b", M, status="hold"),
                make_row("c", M, status="partial"), make_row("d", M, status="pending"),
                make_row("e", M)]
        assert [r[2] for r in queue_order(rows)] == ["c", "d", "e"]

    def test_drop_existing_translations_keeps_outdated_rows(self, tmp_path):
        post = tmp_path / "Aspose.Blog" / "email" / "my-post"
        post.mkdir(parents=True)
        (post / "index.de.md").write_text("x")
        (post / "index.fr.md").write_text("x")
        rows = [make_row(issue=O), make_row(issue=M)]
        remaining, done = drop_existing_translations(rows, str(tmp_path))
        assert [r[5] for r in remaining] == [O]      # MISSING row: all files exist → done
        assert remaining[0][7] == "de, fr"           # OUTDATED row untouched
        assert [r[5] for r in done] == [M]


# ---------------------------------------------------------------------------
# TranslationOrchestrator.translate_files() with an OUTDATED row
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "PRODUCTION_ENV", False)
    monkeypatch.setattr(translator, "send_metrics", lambda *a, **k: None)
    orch = TranslationOrchestrator(api_key="test-key")
    monkeypatch.setattr(orch.platform_agent, "identify_platform", lambda content: "Python")

    written = []

    def fake_translate_file(input_path, lang, domain):
        out = tmp_path / input_path.replace("index.md", f"index.{lang}.md")
        out.write_text(f"new {lang}", encoding="utf-8")
        written.append(lang)
        return str(out)

    monkeypatch.setattr(orch, "translate_file", fake_translate_file)

    comments = []
    real_log = orch.log_post_comment

    done = []

    def spy_log(domain, slug, comment, run_langs=None, done_langs=None):
        text = comment(None) if callable(comment) else comment
        assert "❌ Failed:" not in text, text          # a post error would hide behind the comment
        comments.append(run_langs)
        done.append(done_langs)
        return real_log(domain, slug, comment, run_langs=run_langs, done_langs=done_langs)

    monkeypatch.setattr(orch, "log_post_comment", spy_log)
    orch.written, orch.comments, orch.done = written, comments, done
    return orch


def _post(tmp_path):
    d = tmp_path / "blog-checkedout-repo/content/Aspose.Blog/email/my-post"
    d.mkdir(parents=True)
    (d / "index.md").write_text("---\ntitle: T\n---\n\nBody.\n", encoding="utf-8")
    (d / "index.de.md").write_text("old de", encoding="utf-8")
    return d


class TestTranslateFilesOutdated:
    def test_outdated_row_overwrites_existing_translation(self, orchestrator, tmp_path):
        d = _post(tmp_path)
        stats = orchestrator.translate_files("blog.aspose.com", None, 3, [make_row(issue=O, langs="de")])
        assert orchestrator.written == ["de"]
        assert (d / "index.de.md").read_text(encoding="utf-8") == "new de"
        assert stats.items_succeeded == 1 and stats.items_skipped == 0

    def test_missing_row_still_skips_existing_translation(self, orchestrator, tmp_path):
        d = _post(tmp_path)
        stats = orchestrator.translate_files("blog.aspose.com", None, 3, [make_row(issue=M, langs="de, fr")])
        assert orchestrator.written == ["fr"]
        assert (d / "index.de.md").read_text(encoding="utf-8") == "old de"
        assert stats.items_skipped == 1

    def test_comment_is_logged_for_each_rows_own_languages(self, orchestrator, tmp_path):
        _post(tmp_path)
        orchestrator.translate_files("blog.aspose.com", None, 3,
                                     [make_row(issue=M, langs="fr"), make_row(issue=O, langs="de")])
        assert orchestrator.comments == [["fr"], ["de"]]
        assert orchestrator.done == [["fr"], ["de"]]


# ---------------------------------------------------------------------------
# ISSUE rows, the language budget and the run time limit (Phase 2, 18 Nov 2026)
# ---------------------------------------------------------------------------

from translator import (apply_language_budget, build_history_comment, fill_issue_langs,
                        is_retranslate_row, language_budget, result_head)

I = config.ISSUE_ISSUE


class TestIssueRows:
    def test_issue_rows_pass_the_filter_and_retranslate(self):
        rows = [make_row(issue=I), make_row(issue=E)]
        assert [r[5] for r in filter_valid_rows(rows)] == [I]
        assert is_retranslate_row(make_row(issue=I)) and is_retranslate_row(make_row(issue=O))
        assert not is_retranslate_row(make_row(issue=M))

    def test_blank_issue_languages_mean_all(self):
        (row,) = fill_issue_langs([make_row(issue=I, langs="")], ["de", "fr", "it"])
        assert row[7] == "de, fr, it" and row[6] == "3"

    def test_drop_existing_translations_keeps_issue_rows(self, tmp_path):
        post = tmp_path / "Aspose.Blog" / "email" / "my-post"
        post.mkdir(parents=True)
        (post / "index.de.md").write_text("x")
        (post / "index.fr.md").write_text("x")
        remaining, done = drop_existing_translations([make_row(issue=I)], str(tmp_path))
        assert [r[5] for r in remaining] == [I] and done == []

    def test_issue_row_overwrites_existing_translation(self, orchestrator, tmp_path):
        d = _post(tmp_path)
        orchestrator.translate_files("blog.aspose.com", None, 3, [make_row(issue=I, langs="de")])
        assert (d / "index.de.md").read_text(encoding="utf-8") == "new de"


class TestLanguageBudget:
    def test_budget_is_posts_worth_times_languages(self):
        assert language_budget(3, ["l"] * 21) == 63
        assert language_budget(2, ["l"] * 17) == 34

    def test_many_small_rows_fit(self):
        rows = [make_row(f"p{i}", langs="a, b") for i in range(5)]
        assert [r[2] for r in apply_language_budget(rows, 10)] == ["p0", "p1", "p2", "p3", "p4"]

    def test_row_that_does_not_fit_is_cut_not_skipped(self):
        rows = [make_row("big", langs="a, b, c, d"), make_row("small", langs="a")]
        (cut,) = apply_language_budget(rows, 3)
        assert cut[2] == "big" and cut[7] == "a, b, c" and cut[6] == "3"

    def test_same_language_of_a_post_is_translated_once(self):
        rows = [make_row("p", O, langs="fr, de"), make_row("p", I, langs="fr, it"), make_row("q", I, langs="fr")]
        out = apply_language_budget(rows, 10)
        assert [(r[2], r[5], r[7]) for r in out] == [("p", O, "fr, de"), ("p", I, "it"), ("q", I, "fr")]

    def test_rows_are_not_mutated(self):
        rows = [make_row("big", langs="a, b, c")]
        apply_language_budget(rows, 1)
        assert rows[0][7] == "a, b, c"


class TestTimeLimit:
    def test_no_language_started_after_the_deadline(self, orchestrator, tmp_path, monkeypatch):
        _post(tmp_path)
        clock = iter([0, 10, 10, 10, 100, 100, 100, 100, 100, 100, 100])
        real_time = translator.time.time
        monkeypatch.setattr(translator.time, "time", lambda: next(clock, 100))
        try:
            stats = orchestrator.translate_files("blog.aspose.com", None, 3,
                                                 [make_row(issue=I, langs="de, fr, it"),
                                                  make_row("second", issue=M, langs="fr")],
                                                 deadline=50)
        finally:
            monkeypatch.setattr(translator.time, "time", real_time)
        assert orchestrator.written == ["de"]               # fr / it deferred, second post untouched
        assert orchestrator.comments == [["de", "fr", "it"]]
        assert orchestrator.done == [["de"]]                # only "de" is closed in the queue
        assert stats.items_succeeded == 1

    def test_deferred_languages_are_not_failures(self):
        assert result_head(3, succeeded=["de"], deferred=["fr", "it"]) == "⏸️ Time limit 1/3"
        comment = build_history_comment(total=3, succeeded=["de"], deferred=["fr", "it"], date="D")
        assert comment == "- Date: D\n- ⏸️ Time limit 1/3\n- Not started (run time limit): fr, it"
