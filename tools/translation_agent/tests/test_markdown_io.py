"""
Tests for the pure Markdown file I/O helpers in translator.py
(parse_markdown_file / write_markdown_file). No LLM or network — plain file I/O.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from translator import parse_markdown_file, write_markdown_file


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestParseMarkdownFile:
    def test_parses_frontmatter_and_content(self, tmp_path):
        path = _write(
            tmp_path / "index.md",
            "---\ntitle: Hello\ntags:\n  - a\n  - b\n---\n\nBody text here.\n",
        )
        result = parse_markdown_file(path)
        assert result["frontmatter"]["title"] == "Hello"
        assert result["frontmatter"]["tags"] == ["a", "b"]
        assert "Body text here." in result["content"]

    def test_raises_on_missing_frontmatter(self, tmp_path):
        path = _write(tmp_path / "bad.md", "No front matter here.\n")
        with pytest.raises(ValueError):
            parse_markdown_file(path)

    def test_unicode_frontmatter(self, tmp_path):
        path = _write(tmp_path / "u.md", "---\ntitle: Café déjà\n---\n\nContenu\n")
        result = parse_markdown_file(path)
        assert result["frontmatter"]["title"] == "Café déjà"


class TestWriteMarkdownFile:
    def test_round_trip(self, tmp_path):
        path = str(tmp_path / "out.md")
        fm = {"title": "Hello", "tags": ["a", "b"]}
        body = "Body paragraph."
        status = write_markdown_file(path, fm, body)
        assert status["status"] == "success"
        assert status["file"] == path

        parsed = parse_markdown_file(path)
        assert parsed["frontmatter"]["title"] == "Hello"
        assert parsed["frontmatter"]["tags"] == ["a", "b"]
        assert body in parsed["content"]

    def test_preserves_unicode(self, tmp_path):
        path = str(tmp_path / "u.md")
        write_markdown_file(path, {"title": "Über"}, "Inhalt café")
        parsed = parse_markdown_file(path)
        assert parsed["frontmatter"]["title"] == "Über"
        assert "café" in parsed["content"]
