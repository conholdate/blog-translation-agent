"""
Tests for link_localizer.py — internal links get a language prefix only when
the linked post's translation exists (on disk or queued in the run).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from link_localizer import LinkLocalizer, build_url_index

DOMAIN = "blog.aspose.cloud"


def _post(root, product, folder, url, langs=()):
    d = root / product / folder
    d.mkdir(parents=True)
    (d / "index.md").write_text(f"---\ntitle: T\nurl: {url}\n---\n\nbody\n", encoding="utf-8")
    for lang in langs:
        (d / f"index.{lang}.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")


@pytest.fixture
def localizer(tmp_path):
    _post(tmp_path, "total", "2014-06-02-old-post", "/total/old-post/")                # English only
    _post(tmp_path, "email", "2025-01-01-translated", "/email/translated/", ["fr"])   # has fr
    _post(tmp_path, "email", "2026-10-29-queued", "/email/queued/")                   # fr queued
    loc = LinkLocalizer(DOMAIN, str(tmp_path))
    loc.queue("email", "2026-10-29-queued", " fr")
    return loc


class TestBuildUrlIndex:
    def test_maps_frontmatter_url_to_folder(self, tmp_path):
        _post(tmp_path, "total", "2014-06-02-old-post", "/total/old-post/")
        index = build_url_index(str(tmp_path))
        assert index["/total/old-post/"].name == "2014-06-02-old-post"

    def test_handles_bom_and_quoted_url(self, tmp_path):
        d = tmp_path / "medical" / "p"
        d.mkdir(parents=True)
        (d / "index.md").write_text('﻿---\nurl: "/medical/p"\n---\n', encoding="utf-8")
        assert "/medical/p/" in build_url_index(str(tmp_path))


class TestLocalize:
    def test_untranslated_post_keeps_english_link(self, localizer):
        src = f"[old](https://{DOMAIN}/total/old-post/)"
        assert localizer.localize(src, "fr") == src

    def test_translated_post_gets_prefix(self, localizer):
        src = f"[t](https://{DOMAIN}/email/translated/)"
        assert localizer.localize(src, "fr") == f"[t](https://{DOMAIN}/fr/email/translated/)"

    def test_queued_translation_counts_as_existing(self, localizer):
        src = f"[q](https://{DOMAIN}/email/queued/)"
        assert localizer.localize(src, "fr") == f"[q](https://{DOMAIN}/fr/email/queued/)"

    def test_queue_is_per_language(self, localizer):
        src = f"[q](https://{DOMAIN}/email/queued/)"
        assert localizer.localize(src, "de") == src

    def test_llm_added_prefix_is_removed_when_missing(self, localizer):
        src = f"[old](https://{DOMAIN}/fr/total/old-post/)"
        assert localizer.localize(src, "fr") == f"[old](https://{DOMAIN}/total/old-post/)"

    def test_llm_added_prefix_is_kept_when_present(self, localizer):
        src = f"[t](https://{DOMAIN}/fr/email/translated/)"
        assert localizer.localize(src, "fr") == src

    def test_non_post_links_unchanged(self, localizer):
        src = f"[s](https://{DOMAIN}/total/) [tag](https://{DOMAIN}/tags/email/) [h](https://{DOMAIN}/)"
        assert localizer.localize(src, "fr") == src

    def test_relative_markdown_and_href_links(self, localizer):
        src = '[t](/email/translated/) <a href="/email/translated/">x</a> [o](/total/old-post/)'
        assert localizer.localize(src, "fr") == (
            '[t](/fr/email/translated/) <a href="/fr/email/translated/">x</a> [o](/total/old-post/)'
        )

    def test_query_and_fragment_preserved(self, localizer):
        src = f"[t](https://{DOMAIN}/email/translated/#section)"
        assert localizer.localize(src, "fr") == f"[t](https://{DOMAIN}/fr/email/translated/#section)"

    def test_missing_trailing_slash_still_matches(self, localizer):
        src = f"[t](https://{DOMAIN}/email/translated)"
        assert localizer.localize(src, "fr") == f"[t](https://{DOMAIN}/fr/email/translated)"

    def test_other_domains_unchanged(self, localizer):
        src = "[d](https://docs.aspose.cloud/email/) [b](https://blog.aspose.com/email/translated/)"
        assert localizer.localize(src, "fr") == src

    def test_code_blocks_untouched(self, localizer):
        src = f"```bash\ncurl https://{DOMAIN}/email/translated/\n```\n[t](https://{DOMAIN}/email/translated/)"
        out = localizer.localize(src, "fr")
        assert f"curl https://{DOMAIN}/email/translated/\n" in out
        assert out.endswith(f"[t](https://{DOMAIN}/fr/email/translated/)")
