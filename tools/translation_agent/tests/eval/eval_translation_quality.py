"""
Translation Quality Evaluation Script
======================================
Runs the translation agent on a small set of fixed English blog snippets and
asserts structural + language-shift properties of the output.

Can be run standalone:
    python tools/translation_agent/tests/eval/eval_translation_quality.py

Or discovered by pytest (functions prefixed with test_ are picked up automatically).

Requires PROFESSIONALIZE_API_KEY in the environment.  If the key is absent the
entire eval suite is skipped gracefully — no failures.
"""

import os
import sys
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# ---------------------------------------------------------------------------
# Skip the whole module when no API key is present
# ---------------------------------------------------------------------------
API_KEY = os.getenv("PROFESSIONALIZE_API_KEY", "").strip()
_NO_KEY = not API_KEY

pytestmark = pytest.mark.skipif(
    _NO_KEY,
    reason="PROFESSIONALIZE_API_KEY not set — translation eval skipped",
)


# ---------------------------------------------------------------------------
# Fixed evaluation samples
# Each entry: (slug, english_body, target_lang, target_lang_name)
# ---------------------------------------------------------------------------
EVAL_SAMPLES = [
    (
        "pdf-convert-python",
        (
            "## Convert PDF to Word in Python\n\n"
            "You can convert PDF documents to Word format using the Aspose.PDF library.\n\n"
            "First, install the package using pip:\n\n"
            "```\npip install aspose-pdf\n```\n\n"
            "Then load the document and call the save method with the target format.\n\n"
            "The output file will preserve all formatting and embedded images."
        ),
        "de",
        "German",
    ),
    (
        "merge-excel-csharp",
        (
            "## Merge Excel Files in C#\n\n"
            "Merging multiple Excel workbooks into a single file is straightforward with Aspose.Cells.\n\n"
            "Create a new workbook, then copy worksheets from each source workbook.\n\n"
            "Save the combined workbook to a desired output path."
        ),
        "fr",
        "French",
    ),
    (
        "compress-images-java",
        (
            "## Compress Images in Java\n\n"
            "Aspose.Imaging for Java lets you reduce image file size without significant quality loss.\n\n"
            "Set the compression level and the target format before calling the save method.\n\n"
            "You can also resize the image dimensions as part of the same operation."
        ),
        "es",
        "Spanish",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_translation_api(english_body: str, target_lang: str) -> str:
    """Call the translation agent and return the translated body string."""
    import config
    from openai import OpenAI

    client = OpenAI(api_key=API_KEY, base_url=config.PROFESSIONALIZE_BASE_URL)

    system_prompt = (
        f"You are a professional blog translator. "
        f"Translate the following English Markdown blog post body into {target_lang}. "
        f"Preserve all Markdown formatting, code fences, headings, and shortcodes exactly. "
        f"Do not translate content inside code fences. "
        f"Return only the translated Markdown, no explanation."
    )

    response = client.chat.completions.create(
        model=config.PROFESSIONALIZE_LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": english_body},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def _has_code_fences(text: str) -> bool:
    return bool(re.search(r'```', text))


def _has_headings(text: str) -> bool:
    return bool(re.search(r'^#{1,6}\s', text, re.MULTILINE))


def _length_ratio(original: str, translated: str) -> float:
    if not original:
        return 1.0
    return len(translated) / len(original)


def _words_changed_pct(original: str, translated: str) -> float:
    """Fraction of original word tokens absent from the translation."""
    orig_words  = set(re.sub(r'[^a-zA-Z0-9]', ' ', original).lower().split())
    trans_words = set(re.sub(r'[^a-zA-Z0-9]', ' ', translated).lower().split())
    if not orig_words:
        return 0.0
    changed = orig_words - trans_words
    return len(changed) / len(orig_words) * 100


# ---------------------------------------------------------------------------
# Eval test cases (one per sample, parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("slug,english_body,lang,lang_name", EVAL_SAMPLES)
def test_translation_output_length(slug, english_body, lang, lang_name):
    """Translated output must be 50%–250% the length of the English input."""
    translated = _call_translation_api(english_body, lang_name)
    ratio = _length_ratio(english_body, translated)
    assert 0.50 <= ratio <= 2.50, (
        f"[{slug} → {lang}] Length ratio out of range: {ratio:.2f}\n"
        f"Original length: {len(english_body)}, Translated length: {len(translated)}"
    )


@pytest.mark.parametrize("slug,english_body,lang,lang_name", EVAL_SAMPLES)
def test_translation_preserves_code_fences(slug, english_body, lang, lang_name):
    """If the English body has code fences, the translation must also contain them."""
    if not _has_code_fences(english_body):
        pytest.skip("Sample has no code fences")
    translated = _call_translation_api(english_body, lang_name)
    assert _has_code_fences(translated), (
        f"[{slug} → {lang}] Code fences missing from translated output"
    )


@pytest.mark.parametrize("slug,english_body,lang,lang_name", EVAL_SAMPLES)
def test_translation_preserves_headings(slug, english_body, lang, lang_name):
    """Translated output must preserve Markdown headings."""
    if not _has_headings(english_body):
        pytest.skip("Sample has no headings")
    translated = _call_translation_api(english_body, lang_name)
    assert _has_headings(translated), (
        f"[{slug} → {lang}] Markdown headings missing from translated output"
    )


@pytest.mark.parametrize("slug,english_body,lang,lang_name", EVAL_SAMPLES)
def test_translation_meaningfully_changes_words(slug, english_body, lang, lang_name):
    """At least 30% of English prose words must differ in the translation."""
    translated = _call_translation_api(english_body, lang_name)
    pct = _words_changed_pct(english_body, translated)
    assert pct >= 30.0, (
        f"[{slug} → {lang}] Only {pct:.1f}% of words changed — translation may be incomplete"
    )


@pytest.mark.parametrize("slug,english_body,lang,lang_name", EVAL_SAMPLES)
def test_translation_no_shortcode_leakage(slug, english_body, lang, lang_name):
    """Hugo shortcode syntax must not appear garbled in the output."""
    translated = _call_translation_api(english_body, lang_name)
    # Any {{ or }} that appear should be balanced (not half-broken)
    open_count  = translated.count("{{")
    close_count = translated.count("}}")
    assert open_count == close_count, (
        f"[{slug} → {lang}] Unbalanced shortcode braces in output: "
        f"{{{{ × {open_count}  }}}} × {close_count}"
    )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if _NO_KEY:
        print("⚠️  PROFESSIONALIZE_API_KEY not set — skipping all eval checks.")
        sys.exit(0)

    passed = failed = skipped = 0

    for slug, english_body, lang, lang_name in EVAL_SAMPLES:
        print(f"\n{'='*60}")
        print(f"  Sample : {slug}")
        print(f"  Target : {lang_name} ({lang})")
        print(f"{'='*60}")

        translated = _call_translation_api(english_body, lang_name)
        print(f"  Translated ({len(translated)} chars):\n{translated[:300]}{'...' if len(translated) > 300 else ''}\n")

        checks = [
            ("Length ratio 0.5–2.5",    0.50 <= _length_ratio(english_body, translated) <= 2.50),
            ("Code fences preserved",   not _has_code_fences(english_body) or _has_code_fences(translated)),
            ("Headings preserved",      not _has_headings(english_body) or _has_headings(translated)),
            ("≥30% words changed",      _words_changed_pct(english_body, translated) >= 30.0),
            ("Balanced shortcode braces", translated.count("{{") == translated.count("}}")),
        ]

        for label, result in checks:
            icon = "✅" if result else "❌"
            print(f"  {icon}  {label}")
            if result:
                passed += 1
            else:
                failed += 1

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} checks passed")
    print(f"{'='*60}\n")

    sys.exit(0 if failed == 0 else 1)
