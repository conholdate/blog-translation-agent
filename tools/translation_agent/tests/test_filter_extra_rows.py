"""
Tests for filter_extra_rows() and TranslationOrchestrator.delete_extra_files()
in translator.py.
"""

import pytest
import config
from translator import filter_extra_rows, TranslationOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_row(domain="blog.aspose.com", product="email", slug="my-post",
             url="/email/my-post/", author="John", issue=config.ISSUE_EXTRA,
             count="1", extra="tmp"):
    """Return a well-formed 8-column EXTRA-shaped row."""
    return [domain, product, slug, url, author, issue, count, extra]


# ---------------------------------------------------------------------------
# filter_extra_rows()
# ---------------------------------------------------------------------------

def test_extra_row_is_kept():
    rows = [make_row()]
    assert filter_extra_rows(rows) == rows


def test_missing_issue_row_is_filtered_out():
    # MISSING rows have a non-blank column 7 (langs, not junk filenames) —
    # must still be excluded from deletion based on Issue, not blankness.
    row = make_row(issue=config.ISSUE_MISSING, extra="fr, de")
    assert filter_extra_rows([row]) == []


def test_none_returns_none():
    assert filter_extra_rows(None) is None


def test_empty_list_returns_empty():
    assert filter_extra_rows([]) == []


def test_row_with_empty_extra_filtered():
    assert filter_extra_rows([make_row(extra="")]) == []


def test_row_with_too_few_columns_filtered():
    short_row = ["blog.aspose.com", "email", "my-post"]  # only 3 cols, needs > 7
    assert filter_extra_rows([short_row]) == []


def test_mixed_list_keeps_only_extra_rows():
    missing_row = make_row(slug="post-1", issue=config.ISSUE_MISSING, extra="fr")
    extra_row   = make_row(slug="post-2", issue=config.ISSUE_EXTRA, extra="tmp")
    result = filter_extra_rows([missing_row, extra_row])
    assert result == [extra_row]


# ---------------------------------------------------------------------------
# TranslationOrchestrator.delete_extra_files()
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    # delete_extra_files() reports metrics via send_metrics(), which always
    # posts to the team webhook — keep tests fully offline.
    monkeypatch.setattr("translator.send_metrics", lambda *a, **k: None)


@pytest.fixture
def orchestrator():
    return TranslationOrchestrator(api_key="test-key")


def test_deletes_reconstructed_files(tmp_path, monkeypatch, orchestrator):
    monkeypatch.chdir(tmp_path)
    post_dir = tmp_path / "blog-checkedout-repo/content/Aspose.Blog/email/my-post"
    post_dir.mkdir(parents=True)
    (post_dir / "index.cs.md").write_text("junk")
    (post_dir / "index.pl.md").write_text("junk")

    row = make_row(product="email", slug="my-post", extra="cs, pl")
    stats = orchestrator.delete_extra_files("blog.aspose.com", [row])

    assert not (post_dir / "index.cs.md").exists()
    assert not (post_dir / "index.pl.md").exists()
    assert stats.items_discovered == 2
    assert stats.items_succeeded == 2
    assert stats.items_skipped == 0


def test_missing_reconstructed_file_is_skipped_not_raised(tmp_path, monkeypatch, orchestrator):
    monkeypatch.chdir(tmp_path)
    post_dir = tmp_path / "blog-checkedout-repo/content/Aspose.Blog/email/my-post"
    post_dir.mkdir(parents=True)
    # No file created — a junk file like "readme.md" can't be losslessly
    # reconstructed from its fragment, so the reconstructed path won't exist.
    # This must be skipped, not raise.

    row = make_row(product="email", slug="my-post", extra="md")
    stats = orchestrator.delete_extra_files("blog.aspose.com", [row])

    assert stats.items_discovered == 1
    assert stats.items_succeeded == 0
    assert stats.items_skipped == 1


def test_unknown_domain_is_skipped(tmp_path, monkeypatch, orchestrator):
    monkeypatch.chdir(tmp_path)
    row = make_row(domain="blog.unknown.com", extra="tmp")
    stats = orchestrator.delete_extra_files("blog.unknown.com", [row])
    assert stats.items_discovered == 0


def test_multiple_rows_aggregate_stats(tmp_path, monkeypatch, orchestrator):
    monkeypatch.chdir(tmp_path)
    dir1 = tmp_path / "blog-checkedout-repo/content/Aspose.Blog/email/post-1"
    dir2 = tmp_path / "blog-checkedout-repo/content/Aspose.Blog/pdf/post-2"
    dir1.mkdir(parents=True)
    dir2.mkdir(parents=True)
    (dir1 / "index.cs.md").write_text("junk")
    # dir2's "index.tmp.md" intentionally not created -> skipped

    rows = [
        make_row(product="email", slug="post-1", extra="cs"),
        make_row(product="pdf", slug="post-2", extra="tmp"),
    ]
    stats = orchestrator.delete_extra_files("blog.aspose.com", rows)

    assert stats.items_discovered == 2
    assert stats.items_succeeded == 1
    assert stats.items_skipped == 1
