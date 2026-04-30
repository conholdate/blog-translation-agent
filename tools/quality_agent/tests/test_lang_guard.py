"""
Tests for lang_guard.py — language validation and translation heuristics.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import lang_guard


# ============================================================================
# normalize()
# ============================================================================

class TestNormalize:
    def test_standard_code_passthrough(self):
        assert lang_guard.normalize("de") == "de"

    def test_uppercase_lowercased(self):
        assert lang_guard.normalize("DE") == "de"

    def test_whitespace_stripped(self):
        assert lang_guard.normalize("  fr  ") == "fr"

    def test_zh_tw_maps_to_zh_hant(self):
        assert lang_guard.normalize("zh-tw") == "zh-hant"

    def test_zh_tw_uppercase(self):
        assert lang_guard.normalize("ZH-TW") == "zh-hant"

    def test_zh_hans_maps_to_zh(self):
        assert lang_guard.normalize("zh-hans") == "zh"

    def test_per_maps_to_fa(self):
        assert lang_guard.normalize("per") == "fa"

    def test_heb_maps_to_he(self):
        assert lang_guard.normalize("heb") == "he"

    def test_unknown_code_returned_as_is(self):
        assert lang_guard.normalize("xx") == "xx"


# ============================================================================
# is_valid()
# ============================================================================

class TestIsValid:
    @pytest.mark.parametrize("code", [
        "ar", "cs", "de", "es", "fa", "fr", "he", "id", "it",
        "ja", "ko", "nl", "pl", "pt", "ru", "sv", "th", "tr",
        "uk", "vi", "zh", "zh-hant",
    ])
    def test_known_codes_are_valid(self, code):
        assert lang_guard.is_valid(code) is True

    def test_alias_zh_tw_is_valid(self):
        assert lang_guard.is_valid("zh-tw") is True

    def test_alias_per_is_valid(self):
        assert lang_guard.is_valid("per") is True

    def test_unknown_code_is_invalid(self):
        assert lang_guard.is_valid("xx") is False

    def test_empty_string_is_invalid(self):
        assert lang_guard.is_valid("") is False

    def test_numeric_string_is_invalid(self):
        assert lang_guard.is_valid("123") is False


# ============================================================================
# get_name()
# ============================================================================

class TestGetName:
    def test_known_code_returns_display_name(self):
        assert lang_guard.get_name("de") == "German"
        assert lang_guard.get_name("ja") == "Japanese"
        assert lang_guard.get_name("zh") == "Chinese (Simplified)"

    def test_alias_resolves_to_name(self):
        assert lang_guard.get_name("zh-tw") == "Chinese (Traditional)"

    def test_unknown_code_returns_code_itself(self):
        assert lang_guard.get_name("xx") == "xx"


# ============================================================================
# is_rtl()
# ============================================================================

class TestIsRtl:
    @pytest.mark.parametrize("code", ["ar", "fa", "he"])
    def test_rtl_languages(self, code):
        assert lang_guard.is_rtl(code) is True

    @pytest.mark.parametrize("code", ["de", "fr", "ja", "zh", "ko"])
    def test_ltr_languages(self, code):
        assert lang_guard.is_rtl(code) is False

    def test_alias_per_is_rtl(self):
        assert lang_guard.is_rtl("per") is True


# ============================================================================
# appears_translated()
# ============================================================================

class TestAppearsTranslated:
    def test_clearly_translated_text(self):
        original   = "This is a blog post about document conversion in Python."
        translated = "Dies ist ein Blogbeitrag über Dokumentenkonvertierung in Python."
        assert lang_guard.appears_translated(original, translated) is True

    def test_identical_text_not_translated(self):
        text = "This is a blog post about document conversion."
        assert lang_guard.appears_translated(text, text) is False

    def test_only_code_changed_still_detected(self):
        original   = "The method returns a value. Call it like this."
        translated = "La méthode retourne une valeur. Appelez-la comme ceci."
        assert lang_guard.appears_translated(original, translated) is True

    def test_very_short_text_returns_true_when_nonempty(self):
        assert lang_guard.appears_translated("Hi", "Hola") is True

    def test_identical_empty_strings(self):
        assert lang_guard.appears_translated("", "") is False

    def test_custom_min_change_pct(self):
        original   = "one two three four five six seven eight nine ten"
        # Only 2 words differ — 20% change — passes default threshold exactly
        translated = "one two three four five six seven eight nuevo diez"
        assert lang_guard.appears_translated(original, translated, min_change_pct=20.0) is True

    def test_insufficient_change_below_threshold(self):
        original   = "one two three four five six seven eight nine ten"
        translated = "one two three four five six seven eight nine nuevo"
        # Only 1/10 words differ = 10% — below default 20%
        assert lang_guard.appears_translated(original, translated, min_change_pct=20.0) is False


# ============================================================================
# should_skip_validation()
# ============================================================================

class TestShouldSkipValidation:
    def test_fenced_code_block_skipped(self):
        assert lang_guard.should_skip_validation("```python\nprint('hello')\n```") is True

    def test_frontmatter_divider_skipped(self):
        assert lang_guard.should_skip_validation("---") is True

    def test_hugo_shortcode_skipped(self):
        assert lang_guard.should_skip_validation("{{< youtube abc123 >}}") is True

    def test_normal_paragraph_not_skipped(self):
        assert lang_guard.should_skip_validation("This is a normal paragraph.") is False

    def test_plain_heading_not_skipped(self):
        assert lang_guard.should_skip_validation("## Introduction") is False

    def test_whitespace_only_around_divider(self):
        assert lang_guard.should_skip_validation("  ---  ") is True