"""
Tests for pure helper methods and the argument parser in translator.py.
The agent classes are built with a null client/config — the methods under test
use neither.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from translator import FrontmatterTranslatorAgent, ContentTranslatorAgent, build_parser


@pytest.fixture
def fm_agent():
    return FrontmatterTranslatorAgent(None, None)


@pytest.fixture
def content_agent():
    return ContentTranslatorAgent(None, None)


# ============================================================================
# get_nested_value / set_nested_value  (dot-notation dict helpers)
# ============================================================================

class TestNestedValues:
    def test_get_nested_value_deep(self, fm_agent):
        assert fm_agent.get_nested_value({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_get_nested_value_missing_returns_none(self, fm_agent):
        assert fm_agent.get_nested_value({"a": {}}, "a.b.c") is None

    def test_get_nested_value_top_level(self, fm_agent):
        assert fm_agent.get_nested_value({"x": 1}, "x") == 1

    def test_set_nested_value_creates_path(self, fm_agent):
        data = {}
        fm_agent.set_nested_value(data, "a.b.c", "v")
        assert data == {"a": {"b": {"c": "v"}}}

    def test_set_nested_value_overwrites(self, fm_agent):
        data = {"a": {"b": 1}}
        fm_agent.set_nested_value(data, "a.b", 2)
        assert data["a"]["b"] == 2

    def test_get_after_set_roundtrip(self, fm_agent):
        data = {}
        fm_agent.set_nested_value(data, "meta.title", "Hi")
        assert fm_agent.get_nested_value(data, "meta.title") == "Hi"


# ============================================================================
# _appears_translated  (quick heuristic)
# ============================================================================

class TestAppearsTranslated:
    def test_identical_text_not_translated(self, content_agent):
        text = "This is a fairly long sentence with several distinct words in it."
        assert content_agent._appears_translated(text, text) is False

    def test_changed_text_appears_translated(self, content_agent):
        original = "This is a fairly long sentence with several distinct words in it."
        translated = "Ceci est une phrase assez longue avec plusieurs mots distincts dedans."
        assert content_agent._appears_translated(original, translated) is True

    def test_markdown_stripped_before_compare(self, content_agent):
        # Same words, only markdown/code differs → still "not translated"
        original = "**Hello** world `code`"
        translated = "Hello world `code`"
        assert content_agent._appears_translated(original, translated) is False


# ============================================================================
# build_parser  (argparse)
# ============================================================================

class TestBuildParser:
    def test_minimal_domain_only(self):
        args = build_parser().parse_args(["--domain", "blog.aspose.com"])
        assert args.domain == "blog.aspose.com"
        assert args.key is None
        assert args.limit is None

    def test_domain_is_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_limit_parsed_as_int(self):
        args = build_parser().parse_args(["--domain", "x", "--limit", "5"])
        assert args.limit == 5

    def test_posts_list_parsed_as_json(self):
        args = build_parser().parse_args(["--domain", "x", "--posts-list", '[["a","b"]]'])
        assert args.posts_list == [["a", "b"]]
