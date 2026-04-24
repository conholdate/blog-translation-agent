"""
Tests for filter_valid_rows() in translator.py

Covers the fix that prevents start_translation() from crashing when the
Google Sheet contains only a sentinel row (e.g. '!!! NO MISSING TRANSLATION
FOUND !!!') or otherwise malformed data.
"""

import pytest
from translator import filter_valid_rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_row(domain="blog.aspose.com", product="email", slug="my-post",
             url="/email/my-post/", author="John", extra="", langs="ar, fr"):
    """Return a well-formed 7-column row."""
    return [domain, product, slug, url, author, extra, langs]


# ---------------------------------------------------------------------------
# Valid rows — must be kept
# ---------------------------------------------------------------------------

def test_single_valid_row_is_kept():
    rows = [make_row()]
    assert filter_valid_rows(rows) == rows


def test_multiple_valid_rows_all_kept():
    rows = [make_row(slug="post-1"), make_row(slug="post-2")]
    assert filter_valid_rows(rows) == rows


# ---------------------------------------------------------------------------
# Sentinel / empty inputs — must be dropped or return early
# ---------------------------------------------------------------------------

def test_none_returns_none():
    assert filter_valid_rows(None) is None


def test_empty_list_returns_empty():
    assert filter_valid_rows([]) == []


def test_sentinel_row_is_filtered_out():
    sentinel = ["!!! NO MISSING TRANSLATION FOUND !!!", "", "", "", "", "", ""]
    assert filter_valid_rows([sentinel]) == []


def test_sentinel_with_fewer_columns_is_filtered_out():
    sentinel = ["!!! NO MISSING TRANSLATION FOUND !!!"]
    assert filter_valid_rows([sentinel]) == []


# ---------------------------------------------------------------------------
# Rows with missing required fields — must be dropped
# ---------------------------------------------------------------------------

def test_row_with_empty_domain_filtered():
    assert filter_valid_rows([make_row(domain="")]) == []


def test_row_with_whitespace_domain_filtered():
    assert filter_valid_rows([make_row(domain="   ")]) == []


def test_row_with_empty_product_filtered():
    assert filter_valid_rows([make_row(product="")]) == []


def test_row_with_empty_slug_filtered():
    assert filter_valid_rows([make_row(slug="")]) == []


def test_row_with_empty_langs_filtered():
    assert filter_valid_rows([make_row(langs="")]) == []


def test_row_with_whitespace_langs_filtered():
    assert filter_valid_rows([make_row(langs="   ")]) == []


def test_row_with_too_few_columns_filtered():
    short_row = ["blog.aspose.com", "email", "my-post"]  # only 3 cols, needs > 6
    assert filter_valid_rows([short_row]) == []


def test_row_with_exactly_6_columns_filtered():
    row = ["blog.aspose.com", "email", "my-post", "/url/", "Author", "extra"]
    assert filter_valid_rows([row]) == []


# ---------------------------------------------------------------------------
# Mixed lists — valid rows kept, invalid dropped
# ---------------------------------------------------------------------------

def test_sentinel_mixed_with_valid_rows():
    sentinel = ["!!! NO MISSING TRANSLATION FOUND !!!", "", "", "", "", "", ""]
    valid = make_row()
    result = filter_valid_rows([sentinel, valid])
    assert result == [valid]


def test_blank_row_mixed_with_valid_rows():
    blank = ["", "", "", "", "", "", ""]
    valid = make_row()
    result = filter_valid_rows([blank, valid])
    assert result == [valid]


def test_multiple_invalid_rows_with_one_valid():
    rows = [
        make_row(domain=""),          # missing domain
        make_row(langs=""),           # missing langs
        ["too", "short"],             # too few columns
        make_row(slug="good-post"),   # valid
    ]
    result = filter_valid_rows(rows)
    assert len(result) == 1
    assert result[0][2] == "good-post"


def test_all_invalid_rows_returns_empty():
    rows = [
        make_row(domain=""),
        make_row(product=""),
        make_row(slug=""),
        make_row(langs=""),
    ]
    assert filter_valid_rows(rows) == []
