"""
Tests for translator.py guard/validation helpers — the pure functions behind the
recent shortcode/code-fence translation fixes. No LLM client is required: these
methods are string comparisons, so the agent is built with a null client/config.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from translator import ContentTranslatorAgent, update_url_with_language


@pytest.fixture
def agent():
    # These guard methods use neither self.client nor self.config.
    return ContentTranslatorAgent(None, None)


# ============================================================================
# update_url_with_language
# ============================================================================

class TestUpdateUrlWithLanguage:
    def test_adds_language_prefix_when_missing(self):
        assert update_url_with_language("/barcode/post/", "es") == "/es/barcode/post/"

    def test_leaves_url_untouched_when_prefix_present(self):
        assert update_url_with_language("/es/barcode/post/", "es") == "/es/barcode/post/"

    def test_prefix_is_language_specific(self):
        # A different language's prefix should not count as already-prefixed.
        assert update_url_with_language("/fr/post/", "es") == "/es/fr/post/"


# ============================================================================
# _shortcode_syntax_corrupted  (Hugo shortcode quoting damage)
# ============================================================================

class TestShortcodeSyntaxCorrupted:
    def test_flags_paren_quote_corruption_introduced_by_model(self, agent):
        original = 'image src="img.png"'
        translated = 'image src=("img.png")'           # =(" introduced
        assert agent._shortcode_syntax_corrupted(original, translated) is True

    def test_flags_escaped_quote_corruption(self, agent):
        original = 'image src="img.png"'
        translated = 'image src=\\"img.png\\"'          # =\" introduced
        assert agent._shortcode_syntax_corrupted(original, translated) is True

    def test_clean_translation_is_not_flagged(self, agent):
        original = "Some prose with a shortcode."
        translated = "Algo de prosa con un shortcode."
        assert agent._shortcode_syntax_corrupted(original, translated) is False

    def test_pattern_present_in_original_is_not_flagged(self, agent):
        # If the (unusual) pattern was already in the source, it is not corruption.
        original = 'weird src=("img.png")'
        translated = 'raro src=("img.png")'
        assert agent._shortcode_syntax_corrupted(original, translated) is False


# ============================================================================
# _code_fence_count_mismatched
# ============================================================================

class TestCodeFenceCountMismatched:
    def test_equal_fence_counts_ok(self, agent):
        original = "```py\nprint(1)\n```"
        translated = "```py\nprint(1)\n```"
        assert agent._code_fence_count_mismatched(original, translated) is False

    def test_dropped_closing_fence_flagged(self, agent):
        original = "```py\nprint(1)\n```"
        translated = "```py\nprint(1)"                  # closing ``` dropped
        assert agent._code_fence_count_mismatched(original, translated) is True

    def test_added_fence_flagged(self, agent):
        original = "no code here"
        translated = "no code here\n```"                # spurious fence added
        assert agent._code_fence_count_mismatched(original, translated) is True

    def test_no_fences_either_side_ok(self, agent):
        assert agent._code_fence_count_mismatched("plain", "llano") is False


# ============================================================================
# _should_skip_translation_validation
# ============================================================================

class TestShouldSkipTranslationValidation:
    def test_chunk_with_code_fence_is_skipped(self, agent):
        assert agent._should_skip_translation_validation("```\ncode\n```") is True

    def test_marker_then_fence_is_skipped(self, agent):
        chunk = "<!--[COMPLETE_CODE_SNIPPET_START]-->\n```py\nx = 1\n```"
        assert agent._should_skip_translation_validation(chunk) is True

    def test_frontmatter_divider_is_skipped(self, agent):
        assert agent._should_skip_translation_validation("---") is True

    def test_hugo_shortcode_is_skipped(self, agent):
        assert agent._should_skip_translation_validation('{{< ref "page.md" >}}') is True

    def test_plain_prose_is_not_skipped(self, agent):
        assert agent._should_skip_translation_validation("Just a sentence of prose.") is False
