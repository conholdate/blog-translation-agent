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

    def test_section_and_tag_links_unchanged(self, localizer):
        src = f"[s](https://{DOMAIN}/total/) [tag](https://{DOMAIN}/tags/email/)"
        assert localizer.localize(src, "fr") == src

    def test_llm_added_prefix_removed_from_section(self, localizer):
        src = f"[s](https://{DOMAIN}/fr/total/)"
        assert localizer.localize(src, "fr") == f"[s](https://{DOMAIN}/total/)"

    def test_home_page_gets_prefix(self, localizer):
        # Reference list entry as in convert-doc-to-pdf-with-nodejs (2026-11-26 retranslation)
        src = f"[h](https://{DOMAIN}/)\n[29]: https://{DOMAIN}/\n"
        assert localizer.localize(src, "ko") == f"[h](https://{DOMAIN}/ko/)\n[29]: https://{DOMAIN}/ko/\n"

    @pytest.mark.parametrize("src, expected", [
        (f"[h](https://{DOMAIN})", f"[h](https://{DOMAIN}/ko/)"),
        (f"[29]: https://{DOMAIN}\n", f"[29]: https://{DOMAIN}/ko/\n"),
        (f"Visit https://{DOMAIN}.", f"Visit https://{DOMAIN}/ko/."),
        (f'<a href="https://{DOMAIN}">x</a>', f'<a href="https://{DOMAIN}/ko/">x</a>'),
        (f"<https://{DOMAIN}>", f"<https://{DOMAIN}/ko/>"),
        (f"[h](http://{DOMAIN})", f"[h](http://{DOMAIN}/ko/)"),
    ])
    def test_bare_domain_gets_prefix(self, localizer, src, expected):
        assert localizer.localize(src, "ko") == expected

    @pytest.mark.parametrize("src", [
        f"[x](https://{DOMAIN}.example.com/)",
        f"[x](https://{DOMAIN}-mirror.com/)",
        f"[x](https://{DOMAIN}y/)",
        f"[x](https://{DOMAIN}:8080/)",
    ])
    def test_lookalike_hosts_unchanged(self, localizer, src):
        assert localizer.localize(src, "ko") == src

    def test_home_page_with_llm_prefix_not_doubled(self, localizer):
        src = f"[h](https://{DOMAIN}/ko/) [h2](https://{DOMAIN}/ko)"
        assert localizer.localize(src, "ko") == f"[h](https://{DOMAIN}/ko/) [h2](https://{DOMAIN}/ko/)"

    def test_home_page_relative_and_fragment(self, localizer):
        src = f'[h](/) <a href="/">x</a> [f](https://{DOMAIN}/#latest) [q](https://{DOMAIN}/?s=pdf)'
        assert localizer.localize(src, "ko") == (
            f'[h](/ko/) <a href="/ko/">x</a> [f](https://{DOMAIN}/ko/#latest) [q](https://{DOMAIN}/ko/?s=pdf)'
        )

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
