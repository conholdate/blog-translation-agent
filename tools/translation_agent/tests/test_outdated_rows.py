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

    def spy_log(domain, slug, comment, run_langs=None):
        comments.append(run_langs)
        return real_log(domain, slug, comment, run_langs=run_langs)

    monkeypatch.setattr(orch, "log_post_comment", spy_log)
    orch.written, orch.comments = written, comments
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
