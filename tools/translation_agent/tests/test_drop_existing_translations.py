"""
Tests for drop_existing_translations() — queued sheet rows are checked against
the checked-out repo before the limit is applied, so a stale sheet doesn't
spend the run's limit on posts that are already translated.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from translator import drop_existing_translations, result_head


def _row(slug, langs, domain="blog.aspose.com", product="medical"):
    return [domain, product, slug, "url", "Author", "MISSING",
            str(len(langs.split(","))), langs, "Translate", ""]


def _post(root, slug, existing=(), repo="Aspose.Blog", product="medical"):
    d = root / repo / product / slug
    d.mkdir(parents=True)
    (d / "index.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")
    for lang in existing:
        (d / f"index.{lang}.md").write_text("x", encoding="utf-8")


class TestDropExistingTranslations:
    def test_fully_translated_row_moves_to_done(self, tmp_path):
        _post(tmp_path, "done", existing=["ar", "de"])
        remaining, done = drop_existing_translations([_row("done", "ar, de")], str(tmp_path))
        assert remaining == []
        assert [r[2] for r in done] == ["done"]

    def test_partial_row_keeps_only_missing_langs(self, tmp_path):
        _post(tmp_path, "partial", existing=["ar"])
        remaining, done = drop_existing_translations([_row("partial", "ar, de, fr")], str(tmp_path))
        assert done == []
        assert remaining[0][7] == "de, fr"
        assert remaining[0][6] == "2"

    def test_untouched_row_kept_as_is(self, tmp_path):
        _post(tmp_path, "new")
        row = _row("new", "ar, de")
        remaining, _ = drop_existing_translations([row], str(tmp_path))
        assert remaining == [row]

    def test_original_row_not_mutated(self, tmp_path):
        _post(tmp_path, "partial", existing=["ar"])
        row = _row("partial", "ar, de")
        drop_existing_translations([row], str(tmp_path))
        assert row[7] == "ar, de"

    def test_order_preserved_so_limit_takes_next_post(self, tmp_path):
        _post(tmp_path, "done", existing=["ar"])
        _post(tmp_path, "next")
        _post(tmp_path, "after")
        rows = [_row("done", "ar"), _row("next", "ar"), _row("after", "ar")]
        remaining, _ = drop_existing_translations(rows, str(tmp_path))
        assert [r[2] for r in remaining[:1]] == ["next"]

    def test_unknown_domain_left_for_translate_files(self, tmp_path):
        row = _row("x", "ar", domain="blog.unknown.com")
        remaining, done = drop_existing_translations([row], str(tmp_path))
        assert remaining == [row] and done == []


class TestResultHeadAlreadyTranslated:
    def test_all_existing_is_not_reported_as_translated(self):
        assert result_head(2, succeeded=[], skipped=["ar", "de"]) == "⏭️ Already translated (2/2 existed)"

    def test_mixed_still_counts_as_translated(self):
        assert result_head(2, succeeded=["de"], skipped=["ar"]) == "✅ Translated 2/2"
