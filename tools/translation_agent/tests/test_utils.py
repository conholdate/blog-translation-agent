"""
Tests for utils.py — send_metrics() and related helpers.
HTTP calls are fully mocked; no network access required.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import utils
import config


# ============================================================================
# Helpers
# ============================================================================

def _base_kwargs(**overrides):
    """Return a minimal valid set of keyword args for send_metrics()."""
    defaults = dict(
        run_id="test-run-id",
        status="success",
        run_duration_ms=1000,
        agent_name="test-agent",
        job_type="translate",
        item_name="test-item",
        items_discovered=5,
        items_failed=0,
        items_succeeded=5,
        items_skipped=0,
        website="blog.aspose.com",
    )
    defaults.update(overrides)
    return defaults


# ============================================================================
# send_metrics() — dev endpoint (always called)
# ============================================================================

class TestSendMetricsDev:
    def test_posts_to_dev_endpoint_on_success(self):
        mock_resp = MagicMock(status_code=200)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            utils.send_metrics(**_base_kwargs())
        # Dev endpoint is always called
        calls = [c.args[0] for c in mock_post.call_args_list]
        assert any(config.METRICS_URL_DEV in url for url in calls)

    def test_network_error_does_not_raise(self):
        with patch("requests.post", side_effect=ConnectionError("offline")):
            utils.send_metrics(**_base_kwargs())   # must not raise

    def test_http_error_status_does_not_raise(self):
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        with patch("requests.post", return_value=mock_resp):
            utils.send_metrics(**_base_kwargs())   # must not raise

    def test_payload_contains_required_fields(self):
        captured = {}
        def fake_post(url, json=None, **kwargs):
            captured.update(json or {})
            return MagicMock(status_code=200)

        with patch("requests.post", side_effect=fake_post):
            utils.send_metrics(**_base_kwargs(
                agent_name="my-agent",
                items_discovered=3,
                items_succeeded=2,
                items_failed=1,
            ))

        assert captured.get("agent_name") == "my-agent"
        assert captured.get("items_discovered") == 3
        assert captured.get("items_succeeded") == 2
        assert captured.get("items_failed") == 1

    def test_token_usage_and_api_calls_in_payload(self):
        captured = {}
        def fake_post(url, json=None, **kwargs):
            captured.update(json or {})
            return MagicMock(status_code=200)

        with patch("requests.post", side_effect=fake_post):
            utils.send_metrics(**_base_kwargs(llm_total_tokens=500, llm_call_count=3))

        assert captured.get("token_usage") == 500
        assert captured.get("api_calls_count") == 3


# ============================================================================
# send_metrics() — production endpoint (gated by PRODUCTION_ENV)
# ============================================================================

class TestSendMetricsProd:
    def test_prod_endpoint_not_called_in_dev_mode(self):
        original = config.PRODUCTION_ENV
        config.PRODUCTION_ENV = False
        try:
            with patch("requests.post", return_value=MagicMock(status_code=200)) as mock_post:
                utils.send_metrics(**_base_kwargs())
            urls_called = [c.args[0] for c in mock_post.call_args_list]
            assert not any(config.METRICS_URL in url for url in urls_called if config.METRICS_URL != config.METRICS_URL_DEV)
        finally:
            config.PRODUCTION_ENV = original

    def test_blog_scanner_agent_skips_prod_endpoint(self):
        original = config.PRODUCTION_ENV
        config.PRODUCTION_ENV = True
        try:
            with patch("requests.post", return_value=MagicMock(status_code=200)) as mock_post:
                utils.send_metrics(**_base_kwargs(agent_name=config.AGENT_BLOG_SCANNER))
            urls_called = [c.args[0] for c in mock_post.call_args_list]
            prod_calls = [u for u in urls_called if config.METRICS_URL in u and config.METRICS_URL_DEV not in u]
            assert len(prod_calls) == 0
        finally:
            config.PRODUCTION_ENV = original
