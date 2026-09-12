"""
Tests for build_commit_message.py — no LLM or network, plain file I/O.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from build_commit_message import build_message, group_by_post


def _write(path, title):
    path.write_text(f"---\ntitle: {title}\n---\n\nBody text.\n", encoding="utf-8")
    return str(path)


class TestGroupByPost:
    def test_groups_multiple_languages_of_same_post(self, tmp_path):
        post_dir = tmp_path / "content" / "words" / "my-post"
        post_dir.mkdir(parents=True)
        ja = _write(post_dir / "index.ja.md", "こんにちは")
        fr = _write(post_dir / "index.fr.md", "Bonjour")

        groups = group_by_post([ja, fr])

        assert len(groups) == 1
        group = next(iter(groups.values()))
        assert sorted(group["langs"]) == ["fr", "ja"]
        assert group["title"] in ("こんにちは", "Bonjour")

    def test_ignores_non_markdown_files(self, tmp_path):
        post_dir = tmp_path / "content" / "words" / "my-post"
        post_dir.mkdir(parents=True)
        md = _write(post_dir / "index.ja.md", "Title")
        other = post_dir / "image.png"
        other.write_text("not markdown", encoding="utf-8")

        groups = group_by_post([md, str(other)])

        assert len(groups) == 1
        assert list(groups.values())[0]["files"] == [md]

    def test_falls_back_to_dir_name_on_bad_frontmatter(self, tmp_path):
        post_dir = tmp_path / "content" / "words" / "broken-post"
        post_dir.mkdir(parents=True)
        bad = post_dir / "index.ja.md"
        bad.write_text("no frontmatter here\n", encoding="utf-8")

        groups = group_by_post([str(bad)])

        assert list(groups.values())[0]["title"] == "broken-post"

    def test_prefers_english_source_title_over_translated_title(self, tmp_path):
        post_dir = tmp_path / "content" / "words" / "my-post"
        post_dir.mkdir(parents=True)
        _write(post_dir / "index.md", "My English Title")
        ja = _write(post_dir / "index.ja.md", "私の日本語タイトル")

        groups = group_by_post([ja])

        assert list(groups.values())[0]["title"] == "My English Title"

    def test_falls_back_to_translated_title_when_no_english_source(self, tmp_path):
        post_dir = tmp_path / "content" / "words" / "my-post"
        post_dir.mkdir(parents=True)
        ja = _write(post_dir / "index.ja.md", "私の日本語タイトル")

        groups = group_by_post([ja])

        assert list(groups.values())[0]["title"] == "私の日本語タイトル"


class TestBuildMessage:
    def test_single_post_message(self, tmp_path):
        post_dir = tmp_path / "content" / "words" / "my-post"
        post_dir.mkdir(parents=True)
        ja = _write(post_dir / "index.ja.md", "My Great Post")

        msg = build_message("blog.conholdate.com", [ja])

        title_line = msg.splitlines()[0]
        assert title_line == 'Translate blog post: "My Great Post" (blog.conholdate.com)'
        assert "Files (1):" in msg
        assert ja in msg

    def test_multiple_posts_message(self, tmp_path):
        post_a = tmp_path / "content" / "words" / "post-a"
        post_b = tmp_path / "content" / "words" / "post-b"
        post_a.mkdir(parents=True)
        post_b.mkdir(parents=True)
        a = _write(post_a / "index.ja.md", "Post A")
        b = _write(post_b / "index.fr.md", "Post B")

        msg = build_message("blog.conholdate.com", [a, b])

        title_line = msg.splitlines()[0]
        assert title_line == "Translate 2 blog posts for blog.conholdate.com"
        assert '"Post A"' in msg
        assert '"Post B"' in msg

    def test_no_markdown_files_falls_back_to_static_message(self):
        msg = build_message("blog.conholdate.com", [])
        assert msg == "Daily Blogs Translation: blog.conholdate.com"
