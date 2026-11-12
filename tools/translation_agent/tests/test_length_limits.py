"""Translated titles and descriptions are kept within search-result length (2026-11-12)."""

import translator
from translator import FrontmatterTranslatorAgent, TranslationConfig, display_width


def test_display_width_counts_east_asian_double():
    assert display_width("PDF") == 3
    assert display_width("結合") == 4


def test_long_translation_is_shortened_and_short_one_kept(monkeypatch):
    answers = {"translate": [], "shorten": []}

    def fake_call(client, system, prompt, temperature=0.3, max_tokens=None, model=None):
        if system.startswith("You are a professional technical translator who writes concise"):
            answers["shorten"].append(prompt)
            return "PDF-Dokumente mit der Java Cloud API zusammenführen: Anleitung", translator.TokenUsage(0, 0, 0, "test")
        answers["translate"].append(prompt)
        if "Discover" in prompt:  # the description: short enough
            return "Kurze Beschreibung mit genug Worten für die Suchergebnisse, aber nicht zu lang.", translator.TokenUsage(0, 0, 0, "test")
        return "PDF-Dokumente mit der Java Cloud API zusammenführen: Schritt-für-Schritt-Anleitung", translator.TokenUsage(0, 0, 0, "test")

    monkeypatch.setattr(translator, "call_openai", fake_call)
    agent = FrontmatterTranslatorAgent(client=None, config=TranslationConfig())
    out = agent.translate("blog.example.com", {
        "seoTitle": "Merge PDF Documents Using Java Cloud API: Step-by-Step Guide",
        "description": "Discover how to merge PDF documents using Java cloud API.",
    }, "de")
    assert display_width(out["seoTitle"]) <= 70 and "Anleitung" in out["seoTitle"]
    assert len(answers["shorten"]) == 1  # only the title needed shortening
    assert out["description"].startswith("Kurze")
