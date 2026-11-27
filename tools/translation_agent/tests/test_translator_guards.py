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

    def test_flags_stray_brace_before_closing_delimiter(self, agent):
        # Real failure: broke the Hugo build on a Persian translation.
        original = '{{< figure src="a.jpg" caption="Waterfall chart.">}}'
        translated = '{{< figure src="a.jpg" caption="نمودار آبشاری."}>}}'
        assert agent._shortcode_syntax_corrupted(original, translated) is True

    def test_flags_damaged_closing_delimiter(self, agent):
        original = '{{< figure src="a.jpg" caption="Chart.">}}'
        translated = '{{< figure src="a.jpg" caption="Gráfico."> }}'
        assert agent._shortcode_syntax_corrupted(original, translated) is True

    def test_flags_damaged_opening_delimiter(self, agent):
        original = '{{< figure src="a.jpg" caption="Chart.">}}'
        translated = '{ {< figure src="a.jpg" caption="Gráfico.">}}'
        assert agent._shortcode_syntax_corrupted(original, translated) is True

    def test_clean_shortcode_translation_is_not_flagged(self, agent):
        # Added space before >}} is valid Hugo and common in real translations.
        original = '{{< figure src="a.jpg" caption="Chart.">}}'
        translated = '{{< figure src="a.jpg" caption="Gráfico." >}}'
        assert agent._shortcode_syntax_corrupted(original, translated) is False

    def test_brace_already_in_original_caption_is_not_flagged(self, agent):
        original = '{{< figure src="a.jpg" caption={x}>}}'
        translated = '{{< figure src="a.jpg" caption={x}>}}'
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


# ============================================================================
# Code blocks never reach the model (code_blocks.py) — 27 Nov 2026, ec990f7b on
# blog.groupdocs.cloud: fences moved at blank lines and code comments translated.
# ============================================================================

import re as _re
from types import SimpleNamespace

import translator as _translator
from code_blocks import (protect_code_blocks, restore_code_blocks, placeholders_intact,
                         only_placeholders, code_block_problem, CodeBlockMismatch)

CSV_TO_JPG = """\
Configure the client first.

<!--[CODE_SNIPPET_START]-->
```python
from groupdocs_conversion_cloud import Configuration, ApiClient

# -------------------- Configuration --------------------
configuration = Configuration()
configuration.client_id = "YOUR_CLIENT_ID"

api_client = ApiClient(configuration)
```
<!--[CODE_SNIPPET_END]-->

Then convert the file."""


def _fake_model(transform):
    """call_openai stand-in: the chunk is the text after the prompt's last header line."""
    sent = []

    def call(client, system_prompt, prompt, temperature=0.3, **kw):
        chunk = prompt.split("Below is the Markdown content to translate:\n", 1)[1].strip()
        chunk = "\n".join(l.strip() for l in chunk.split("\n"))
        sent.append(chunk)
        return transform(chunk), None
    call.sent = sent
    return call


def _german(chunk):
    """'Translates' every prose line, keeps placeholder lines (a well-behaved model)."""
    return "\n".join(l if (not l or l.startswith("⟦")) else "DE " + l for l in chunk.split("\n"))


@pytest.fixture
def content_agent(monkeypatch):
    cfg = SimpleNamespace(product_examples=[], language_names={"de": "German"})
    a = ContentTranslatorAgent(None, cfg)
    a.notes = _translator.Counter()
    monkeypatch.setattr(a, "_appears_translated", lambda o, t: True)
    return a


class TestProtectCodeBlocks:
    def test_block_with_blank_lines_and_markers_becomes_one_placeholder(self):
        text, blocks = protect_code_blocks(CSV_TO_JPG)
        assert text == "Configure the client first.\n\n⟦CODE_0⟧\n\nThen convert the file."
        assert blocks[0].startswith("<!--[CODE_SNIPPET_START]-->\n```python")
        assert blocks[0].endswith("```\n<!--[CODE_SNIPPET_END]-->")
        assert restore_code_blocks(text, blocks) == CSV_TO_JPG

    def test_two_blocks_in_a_row_without_text(self):
        src = "Intro\n\n```bash\npip install x\n```\n```python\nimport x\n```\n\nEnd"
        text, blocks = protect_code_blocks(src)
        assert text == "Intro\n\n⟦CODE_0⟧\n⟦CODE_1⟧\n\nEnd"
        assert restore_code_blocks(text, blocks) == src

    def test_markdown_looking_lines_and_fence_in_string_stay_inside(self):
        src = ('```python\n# comment\n- item\n\n## not a heading\nprint("```")\n```\nAfter')
        text, blocks = protect_code_blocks(src)
        assert text == "⟦CODE_0⟧\nAfter"
        assert blocks == [src[:-len("\nAfter")]]

    def test_complete_marker_with_blank_line_and_tilde_fence(self):
        src = "<!--[COMPLETE_CODE_SNIPPET_START]-->\n\n~~~java\nint a;\n\nint b;\n~~~\n\n<!--[COMPLETE_CODE_SNIPPET_END]-->\nText"
        text, blocks = protect_code_blocks(src)
        assert text == "⟦CODE_0⟧\nText"
        assert restore_code_blocks(text, blocks) == src

    def test_indented_block_in_a_list_keeps_its_indent(self):
        src = "1. Install:\n\n   ```bash\n   pip install x\n   ```\n2. Run"
        text, blocks = protect_code_blocks(src)
        assert text == "1. Install:\n\n   ⟦CODE_0⟧\n2. Run"
        assert restore_code_blocks(text.replace("   ⟦", "⟦"), blocks) == src

    def test_unclosed_block_runs_to_the_end(self):
        text, blocks = protect_code_blocks("Text\n```python\nx = 1\n\ny = 2")
        assert text == "Text\n⟦CODE_0⟧" and blocks == ["```python\nx = 1\n\ny = 2"]

    def test_no_code_is_unchanged(self):
        assert protect_code_blocks("Just `inline` code\n\nand text") == ("Just `inline` code\n\nand text", [])


class TestPlaceholdersIntact:
    def test_same_order_own_lines(self):
        assert placeholders_intact("A\n⟦CODE_0⟧\nB\n⟦CODE_1⟧", "X\n⟦CODE_0⟧\nY\n⟦CODE_1⟧")

    @pytest.mark.parametrize("bad", [
        "X\nY",                                 # dropped
        "X\n⟦CODE_1⟧\n⟦CODE_0⟧",                 # reordered
        "X ⟦CODE_0⟧\n⟦CODE_1⟧",                  # glued to text
        "X\n⟦CODE_0⟧\n⟦CODE_1⟧\n⟦CODE_1⟧",       # duplicated
        "X\n⟦CÓDIGO_0⟧\n⟦CODE_1⟧",               # translated
    ])
    def test_rejected(self, bad):
        assert not placeholders_intact("A\n⟦CODE_0⟧\nB\n⟦CODE_1⟧", bad)

    def test_only_placeholders(self):
        assert only_placeholders("⟦CODE_0⟧\n\n⟦CODE_1⟧")
        assert not only_placeholders("Text\n⟦CODE_0⟧")
        assert not only_placeholders("")


class TestCodeBlockProblem:
    def test_identical_code_passes(self):
        assert code_block_problem(CSV_TO_JPG, CSV_TO_JPG.replace("Configure", "Konfigurieren")) is None

    def test_moved_fence_with_same_count_is_rejected(self):
        """The ec990f7b damage: the closing ``` moved up to after line 1 — count unchanged."""
        broken = CSV_TO_JPG.replace(
            "ApiClient\n\n# ----", "ApiClient\n```\n\n# ----").replace(
            "api_client = ApiClient(configuration)\n```\n", "api_client = ApiClient(configuration)\n")
        assert broken.count("```") == CSV_TO_JPG.count("```")
        assert code_block_problem(CSV_TO_JPG, broken) is not None

    def test_translated_comment_is_rejected(self):
        tr = CSV_TO_JPG.replace("# -------------------- Configuration", "# -------------------- Konfiguration")
        assert code_block_problem(CSV_TO_JPG, tr) == "code block 1 (```python) differs from the English"

    def test_changed_info_string_is_rejected(self):
        assert code_block_problem(CSV_TO_JPG, CSV_TO_JPG.replace("```python", "```py")) is not None

    def test_leftover_placeholder_is_rejected(self):
        assert code_block_problem("Text", "Text ⟦CODE_0⟧") == "a code placeholder was left in the text"


class TestTranslateMarkdownWithPlaceholders:
    def test_code_and_its_comments_come_back_unchanged(self, content_agent, monkeypatch):
        fake = _fake_model(_german)
        monkeypatch.setattr(_translator, "call_openai", fake)
        protected, blocks = protect_code_blocks(CSV_TO_JPG)

        out = restore_code_blocks(content_agent._translate_markdown("blog.groupdocs.cloud", protected, "de"), blocks)

        assert "DE Configure the client first." in out and "DE Then convert the file." in out
        assert "# -------------------- Configuration --------------------" in out
        assert code_block_problem(CSV_TO_JPG, out) is None
        assert not any("```" in s or "ApiClient" in s for s in fake.sent)   # code never sent
        assert "⟦CODE_0⟧" not in fake.sent                                  # code-only chunk skipped

    def test_model_that_moves_a_placeholder_keeps_the_english_chunk(self, content_agent, monkeypatch):
        glue = lambda c: _re.sub(r"\n(⟦CODE_\d+⟧)", r" \1", _german(c))
        fake = _fake_model(glue)
        monkeypatch.setattr(_translator, "call_openai", fake)
        chunk = "Configure the client first:\n⟦CODE_0⟧"

        assert content_agent._translate_content_chunk("blog.groupdocs.cloud", chunk, "de") == chunk
        assert len(fake.sent) == 3
        assert content_agent.notes["kept in English (code placeholder)"] == 1

    def test_retry_fixes_a_moved_placeholder(self, content_agent, monkeypatch):
        calls = {"n": 0}

        def flaky(c):
            calls["n"] += 1
            return _re.sub(r"\n(⟦CODE_\d+⟧)", r" \1", _german(c)) if calls["n"] == 1 else _german(c)
        monkeypatch.setattr(_translator, "call_openai", _fake_model(flaky))

        out = content_agent._translate_content_chunk("d", "Configure the client first:\n⟦CODE_0⟧", "de")
        assert out == "DE Configure the client first:\n⟦CODE_0⟧"


class TestTranslateFileCodeCheck:
    """translate_file(): code is protected, restored, checked; a mismatch writes nothing."""

    def _orchestrator(self, content_agent):
        return SimpleNamespace(
            frontmatter_agent=SimpleNamespace(name="fm", translate=lambda d, fm, l: fm),
            content_agent=content_agent,
            get_link_localizer=lambda d: SimpleNamespace(localize=lambda text, lang: text),
        )

    def _post(self, tmp_path):
        p = tmp_path / "index.md"
        p.write_text("---\ntitle: CSV to JPG\n---\n\n" + CSV_TO_JPG + "\n", encoding="utf-8")
        return p

    def test_good_translation_is_written_with_identical_code(self, tmp_path, content_agent, monkeypatch):
        monkeypatch.setattr(_translator, "call_openai", _fake_model(_german))
        post = self._post(tmp_path)

        _translator.TranslationOrchestrator.translate_file(self._orchestrator(content_agent), str(post), "de", "d")

        de = (tmp_path / "index.de.md").read_text(encoding="utf-8")
        assert code_block_problem(CSV_TO_JPG, de) is None and "DE Then convert the file." in de

    def test_code_changed_after_restore_raises_and_writes_nothing(self, tmp_path, content_agent, monkeypatch):
        monkeypatch.setattr(_translator, "call_openai", _fake_model(_german))
        monkeypatch.setattr(_translator, "restore_code_blocks",
                            lambda text, blocks: text.replace("⟦CODE_0⟧", blocks[0].replace("Configuration -", "Konfiguration -")))
        post = self._post(tmp_path)

        with pytest.raises(CodeBlockMismatch):
            _translator.TranslationOrchestrator.translate_file(self._orchestrator(content_agent), str(post), "de", "d")
        assert not (tmp_path / "index.de.md").exists()


def test_failed_reason_is_shown_in_the_comment():
    from translator import build_history_comment
    comment = build_history_comment(total=3, succeeded=["fr"], failed=["de", "it"], date="D",
                                    failed_reasons={"de": "code blocks changed"})
    assert "- Failed: de (code blocks changed), it" in comment
