"""
Language Guard
==============
Utilities used by the quality_agent to validate language codes and
assess whether translated content appears genuinely translated.
"""

import re


# ============================================================================
# LANGUAGE METADATA
# ============================================================================

# Canonical language codes → display names
# Covers all codes used across the six blog domains (config.LANGS_*)
SUPPORTED_LANGUAGES: dict[str, str] = {
    "ar":       "Arabic",
    "cs":       "Czech",
    "da":       "Danish",
    "de":       "German",
    "el":       "Greek",
    "es":       "Spanish",
    "fa":       "Persian",
    "fi":       "Finnish",
    "fr":       "French",
    "he":       "Hebrew",
    "hu":       "Hungarian",
    "id":       "Indonesian",
    "it":       "Italian",
    "ja":       "Japanese",
    "ka":       "Georgian",
    "ko":       "Korean",
    "nl":       "Dutch",
    "no":       "Norwegian",
    "pl":       "Polish",
    "pt":       "Portuguese",
    "ru":       "Russian",
    "sv":       "Swedish",
    "th":       "Thai",
    "tr":       "Turkish",
    "uk":       "Ukrainian",
    "vi":       "Vietnamese",
    "zh":       "Chinese (Simplified)",
    "zh-hant":  "Chinese (Traditional)",
    "zh-tw":    "Chinese (Traditional)",
}

# Right-to-left language codes
RTL_LANGS: set[str] = {"ar", "fa", "he", "ur"}

# Non-canonical → canonical normalisation map
_NORMALIZE_MAP: dict[str, str] = {
    "zh-tw":    "zh-hant",
    "zhtw":     "zh-hant",
    "zh_tw":    "zh-hant",
    "zh-hans":  "zh",
    "zh_hant":  "zh-hant",
    "per":      "fa",
    "heb":      "he",
}


# ============================================================================
# PUBLIC HELPERS
# ============================================================================

def normalize(lang_code: str) -> str:
    """
    Return the canonical form of a language code.
        "zh-tw"  → "zh-hant"
        "ZH-TW"  → "zh-hant"
        "de"     → "de"
    """
    return _NORMALIZE_MAP.get(lang_code.strip().lower(), lang_code.strip().lower())


def is_valid(lang_code: str) -> bool:
    """Return True if the code (after normalization) is in the supported set."""
    return normalize(lang_code) in SUPPORTED_LANGUAGES


def get_name(lang_code: str) -> str:
    """Return the display name for a language code, or the code itself if unknown."""
    return SUPPORTED_LANGUAGES.get(normalize(lang_code), lang_code)


def is_rtl(lang_code: str) -> bool:
    """Return True if the language is right-to-left."""
    return normalize(lang_code) in RTL_LANGS


# ============================================================================
# TRANSLATION QUALITY HEURISTICS
# ============================================================================

def appears_translated(original: str, translated: str, min_change_pct: float = 20.0) -> bool:
    """
    Heuristic: did the translation meaningfully change the text?

    Strips markdown syntax, links, code blocks, and inline code before
    comparing word sets.  Returns True when enough words differ to suggest
    a real translation took place.

    Args:
        original:        Source (English) paragraph.
        translated:      Output from the translation step.
        min_change_pct:  Minimum % of words that must differ (default 20 %).
    """

    def _clean(text: str) -> str:
        text = re.sub(r'[*_`#]', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)           # links → anchor text
        text = re.sub(r'```[^\n]*\n.*?```', '', text, flags=re.DOTALL)  # fenced code blocks
        text = re.sub(r'`[^`]*`', '', text)                             # inline code
        text = re.sub(r'\s+', ' ', text).strip()
        return text.lower()

    orig_clean  = _clean(original)
    trans_clean = _clean(translated)

    if orig_clean == trans_clean:
        return False

    orig_words  = set(orig_clean.split())
    trans_words = set(trans_clean.split())

    if len(orig_words) <= 2:                    # too short to measure reliably
        return len(trans_words) > 0

    changed_pct = len(orig_words - trans_words) / len(orig_words) * 100
    return changed_pct >= min_change_pct


def should_skip_validation(chunk: str) -> bool:
    """
    Return True for chunks whose quality cannot be measured by text-diff
    heuristics: fenced code blocks, Hugo shortcodes, and front-matter dividers.
    """
    s = chunk.strip()
    if s.startswith('```') or s.endswith('```'):
        return True
    if s == '---':
        return True
    if '{{<' in s and '>}}' in s:
        return True
    return False
