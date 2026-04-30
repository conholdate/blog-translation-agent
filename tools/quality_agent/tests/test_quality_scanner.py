"""
Tests for quality_scanner.py helper functions.

Only the pure helper functions are tested here — no Google Sheets, no LLM calls,
no filesystem traversal.  File-reading helpers are tested with temporary files.
"""

import pytest
import sys
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "translation_agent"))

from quality_scanner import (
    _pct_to_float,
    _parse_original_metadata,
    _strip_frontmatter,
    _build_translated_url,
    _heuristic_error_pct,
)


# ============================================================================
# _pct_to_float()
# ============================================================================

class TestPctToFloat:
    def test_integer_percentage(self):
        assert _pct_to_float("60%") == 60.0

    def test_zero_percentage(self):
        assert _pct_to_float("0%") == 0.0

    def test_hundred_percentage(self):
        assert _pct_to_float("100%") == 100.0

    def test_decimal_percentage(self):
        assert _pct_to_float("33.5%") == 33.5

    def test_blank_string_returns_zero(self):
        assert _pct_to_float("") == 0.0

    def test_none_like_string_returns_zero(self):
        assert _pct_to_float("n/a") == 0.0

    def test_whitespace_percentage(self):
        assert _pct_to_float("  75%  ") == 75.0

    def test_no_percent_sign(self):
        assert _pct_to_float("50") == 50.0


# ============================================================================
# _strip_frontmatter()
# ============================================================================

class TestStripFrontmatter:
    def test_removes_yaml_frontmatter(self):
        text = "---\ntitle: Hello\n---\nBody content here."
        assert _strip_frontmatter(text) == "Body content here."

    def test_text_without_frontmatter_returned_as_is(self):
        text = "Just a plain paragraph."
        assert _strip_frontmatter(text) == text

    def test_multiline_body_preserved(self):
        text = "---\ntitle: Test\n---\nLine one.\n\nLine two."
        assert _strip_frontmatter(text) == "Line one.\n\nLine two."


# ============================================================================
# _build_translated_url()
# ============================================================================

class TestBuildTranslatedUrl:
    def test_standard_url_construction(self):
        result = _build_translated_url("blog.aspose.com", "pt", "/3d/convert-obj/")
        assert result == "https://blog.aspose.com/pt/3d/convert-obj/"

    def test_url_without_leading_slash_gets_one(self):
        result = _build_translated_url("blog.groupdocs.com", "de", "viewer/render-pdf/")
        assert result == "https://blog.groupdocs.com/de/viewer/render-pdf/"

    def test_empty_post_url_returns_empty(self):
        assert _build_translated_url("blog.aspose.com", "ja", "") == ""

    def test_double_slash_normalized(self):
        result = _build_translated_url("blog.aspose.cloud", "fr", "//slides/export/")
        assert result == "https://blog.aspose.cloud/fr/slides/export/"


# ============================================================================
# _parse_original_metadata()
# ============================================================================

class TestParseOriginalMetadata:
    def test_reads_url_and_single_author(self, tmp_path):
        md = tmp_path / "index.md"
        md.write_text(textwrap.dedent("""\
            ---
            title: Test Post
            url: /net/convert-pdf/
            author: John Doe
            ---
            Body text here.
        """), encoding="utf-8")
        url, author = _parse_original_metadata(md)
        assert url == "/net/convert-pdf/"
        assert author == "John Doe"

    def test_reads_authors_list_picks_first(self, tmp_path):
        md = tmp_path / "index.md"
        md.write_text(textwrap.dedent("""\
            ---
            url: /net/example/
            authors:
              - Alice
              - Bob
            ---
        """), encoding="utf-8")
        url, author = _parse_original_metadata(md)
        assert author == "Alice"

    def test_missing_frontmatter_returns_empty(self, tmp_path):
        md = tmp_path / "index.md"
        md.write_text("Just plain content, no frontmatter.", encoding="utf-8")
        url, author = _parse_original_metadata(md)
        assert url == ""
        assert author == ""

    def test_nonexistent_file_returns_empty(self, tmp_path):
        url, author = _parse_original_metadata(tmp_path / "missing.md")
        assert url == ""
        assert author == ""

    def test_corrupt_yaml_returns_empty(self, tmp_path):
        md = tmp_path / "index.md"
        md.write_text("---\n: invalid: yaml: [\n---\nbody", encoding="utf-8")
        url, author = _parse_original_metadata(md)
        assert url == ""
        assert author == ""


# ============================================================================
# _heuristic_error_pct()
# ============================================================================

class TestHeuristicErrorPct:
    def _write_md(self, path: Path, frontmatter: str, body: str) -> Path:
        path.write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
        return path

    def test_fully_translated_content_low_error(self, tmp_path):
        orig = self._write_md(
            tmp_path / "index.md",
            "title: Test",
            "This is a paragraph about document conversion.\n\nAnother paragraph with details.",
        )
        trans = self._write_md(
            tmp_path / "index.de.md",
            "title: Test",
            "Dies ist ein Absatz über die Dokumentenkonvertierung.\n\nEin weiterer Absatz mit Details.",
        )
        pct = _heuristic_error_pct(orig, trans, lang="de")
        assert pct < 50.0

    def test_untranslated_content_high_error(self, tmp_path):
        body = (
            "This is a paragraph about document conversion in Python.\n\n"
            "Another paragraph explaining the API usage in detail."
        )
        orig  = self._write_md(tmp_path / "index.md",    "title: T", body)
        trans = self._write_md(tmp_path / "index.fr.md", "title: T", body)
        pct = _heuristic_error_pct(orig, trans, lang="fr")
        assert pct == 100.0

    def test_missing_file_returns_zero(self, tmp_path):
        orig  = tmp_path / "index.md"
        trans = tmp_path / "index.de.md"
        pct = _heuristic_error_pct(orig, trans)
        assert pct == 0.0

    def test_only_code_blocks_returns_zero(self, tmp_path):
        body = "```python\nprint('hello')\n```"
        orig  = self._write_md(tmp_path / "index.md",    "title: T", body)
        trans = self._write_md(tmp_path / "index.ja.md", "title: T", body)
        pct = _heuristic_error_pct(orig, trans, lang="ja")
        assert pct == 0.0
