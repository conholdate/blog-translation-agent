"""
Tests for config.py — validates that all required constants are present and well-formed.
No external calls; purely inspects the module.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


# ============================================================================
# Domain constants
# ============================================================================

class TestDomainConstants:
    EXPECTED_DOMAINS = [
        config.DOMAIN_ASPOSE_COM,
        config.DOMAIN_ASPOSE_CLOUD,
        config.DOMAIN_GROUPDOCS_COM,
        config.DOMAIN_GROUPDOCS_CLOUD,
        config.DOMAIN_CONHOLDATE_COM,
        config.DOMAIN_CONHOLDATE_CLOUD,
    ]

    def test_all_domain_strings_nonempty(self):
        for d in self.EXPECTED_DOMAINS:
            assert isinstance(d, str) and d.strip(), f"Domain constant is empty: {d!r}"

    def test_domain_strings_contain_dot(self):
        for d in self.EXPECTED_DOMAINS:
            assert "." in d, f"Domain looks malformed: {d!r}"

    def test_domains_data_has_all_domains(self):
        for d in self.EXPECTED_DOMAINS:
            assert d in config.domains_data, f"Domain missing from domains_data: {d}"

    def test_domains_data_has_required_keys(self):
        required = {
            config.KEY_SHEET_ID,
            config.KEY_LOCAL_GITHUB_REPO,
            config.KEY_SUPPORTED_LANGS,
        }
        for domain, data in config.domains_data.items():
            for key in required:
                assert key in data, f"domains_data['{domain}'] missing key '{key}'"


# ============================================================================
# LLM / API configuration
# ============================================================================

class TestLLMConfig:
    def test_professionalize_base_url_nonempty(self):
        assert isinstance(config.PROFESSIONALIZE_BASE_URL, str)
        assert config.PROFESSIONALIZE_BASE_URL.startswith("http")

    def test_professionalize_llm_model_nonempty(self):
        assert isinstance(config.PROFESSIONALIZE_LLM_MODEL, str)
        assert config.PROFESSIONALIZE_LLM_MODEL.strip() != ""


# ============================================================================
# Metrics configuration
# ============================================================================

class TestMetricsConfig:
    def test_metrics_url_dev_nonempty(self):
        assert isinstance(config.METRICS_URL_DEV, str)
        assert config.METRICS_URL_DEV.startswith("http")

    def test_metrics_token_dev_nonempty(self):
        assert isinstance(config.METRICS_TOKEN_DEV, str)
        assert config.METRICS_TOKEN_DEV.strip() != ""


# ============================================================================
# Language strings
# ============================================================================

class TestLanguageStrings:
    LANG_ATTRS = [
        "LANGS_ASPOSE_COM",
        "LANGS_GROUPDOCS_COM",
        "LANGS_CONHOLDATE_COM",
        "LANGS_ASPOSE_CLOUD",
        "LANGS_GROUPDOCS_CLOUD",
        "LANGS_CONHOLDATE_CLOUD",
    ]

    def test_lang_strings_are_pipe_separated(self):
        for attr in self.LANG_ATTRS:
            val = getattr(config, attr)
            assert "|" in val, f"{attr} should be pipe-separated but got: {val!r}"

    def test_lang_strings_nonempty(self):
        for attr in self.LANG_ATTRS:
            val = getattr(config, attr)
            assert val.strip() != "", f"{attr} is empty"

    def test_all_lang_codes_at_least_two_chars(self):
        for attr in self.LANG_ATTRS:
            for code in getattr(config, attr).split("|"):
                assert len(code.strip()) >= 2, f"Short lang code '{code}' in {attr}"


# ============================================================================
# PRODUCT_MAP
# ============================================================================

class TestProductMap:
    def test_product_map_exists_and_nonempty(self):
        assert hasattr(config, "PRODUCT_MAP")
        assert isinstance(config.PRODUCT_MAP, dict)
        assert len(config.PRODUCT_MAP) > 0

    def test_product_map_domain_entries_are_dicts(self):
        for domain in [
            config.DOMAIN_ASPOSE_COM,
            config.DOMAIN_GROUPDOCS_COM,
            config.DOMAIN_CONHOLDATE_COM,
        ]:
            assert domain in config.PRODUCT_MAP, f"Domain '{domain}' missing from PRODUCT_MAP"
            assert isinstance(config.PRODUCT_MAP[domain], dict), \
                f"PRODUCT_MAP['{domain}'] should be a dict"
