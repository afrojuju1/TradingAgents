"""Tests for TRADINGAGENTS_* env-var overlay onto DEFAULT_CONFIG."""

from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config_module


def _reload_with_env(monkeypatch, **overrides):
    """Set/clear env vars then reload default_config to re-evaluate DEFAULT_CONFIG."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key in list(default_config_module._NESTED_ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("EDGAR_IDENTITY", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_RUN_PROFILE", raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


def test_no_env_uses_built_in_defaults(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gpt-5.4"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gpt-5.4-mini"
    assert dc.DEFAULT_CONFIG["run_profile"] is None
    assert dc.DEFAULT_CONFIG["selected_analysts"] == [
        "market",
        "social",
        "news",
        "fundamentals",
    ]
    assert dc.DEFAULT_CONFIG["backend_url"] is None
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 1
    assert dc.DEFAULT_CONFIG["checkpoint_enabled"] is False
    assert dc.DEFAULT_CONFIG["parallel_analysts"] is False
    assert dc.DEFAULT_CONFIG["parallel_analyst_workers"] == 4
    assert dc.DEFAULT_CONFIG["analyst_max_tool_iterations"] == 12
    assert dc.DEFAULT_CONFIG["prefetch_data_enabled"] is False
    assert dc.DEFAULT_CONFIG["prefetch_workers"] == 4
    assert dc.DEFAULT_CONFIG["data_tool_cache_enabled"] is False
    assert dc.DEFAULT_CONFIG["data_tool_cache_ttl_seconds"] == 21600
    assert dc.DEFAULT_CONFIG["sec_identity"] is None
    assert dc.DEFAULT_CONFIG["sec_proxy_url"] is None
    assert dc.DEFAULT_CONFIG["sec_use_gluetun"] is False
    assert dc.DEFAULT_CONFIG["sec_request_timeout"] == 30


def test_string_overrides(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_PROVIDER="google",
        TRADINGAGENTS_DEEP_THINK_LLM="gemini-3-pro-preview",
        TRADINGAGENTS_QUICK_THINK_LLM="gemini-3-flash-preview",
        TRADINGAGENTS_LLM_BACKEND_URL="https://example.invalid/v1",
        TRADINGAGENTS_OUTPUT_LANGUAGE="Chinese",
        TRADINGAGENTS_SEC_IDENTITY="Research Bot research@example.com",
        TRADINGAGENTS_SEC_PROXY_URL="http://proxy.example:8888",
        TRADINGAGENTS_GLUETUN_ENV_PATH="/tmp/gluetun.env",
    )
    assert dc.DEFAULT_CONFIG["llm_provider"] == "google"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gemini-3-pro-preview"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gemini-3-flash-preview"
    assert dc.DEFAULT_CONFIG["backend_url"] == "https://example.invalid/v1"
    assert dc.DEFAULT_CONFIG["output_language"] == "Chinese"
    assert dc.DEFAULT_CONFIG["sec_identity"] == "Research Bot research@example.com"
    assert dc.DEFAULT_CONFIG["sec_proxy_url"] == "http://proxy.example:8888"
    assert dc.DEFAULT_CONFIG["gluetun_env_path"] == "/tmp/gluetun.env"


def test_int_coercion(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="3",
        TRADINGAGENTS_MAX_RISK_ROUNDS="2",
        TRADINGAGENTS_PARALLEL_ANALYST_WORKERS="2",
        TRADINGAGENTS_ANALYST_MAX_TOOL_ITERATIONS="10",
        TRADINGAGENTS_DATA_TOOL_CACHE_TTL_SECONDS="60",
        TRADINGAGENTS_SEC_REQUEST_TIMEOUT="45",
        TRADINGAGENTS_PREFETCH_WORKERS="3",
    )
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 3
    assert isinstance(dc.DEFAULT_CONFIG["max_debate_rounds"], int)
    assert dc.DEFAULT_CONFIG["max_risk_discuss_rounds"] == 2
    assert isinstance(dc.DEFAULT_CONFIG["max_risk_discuss_rounds"], int)
    assert dc.DEFAULT_CONFIG["parallel_analyst_workers"] == 2
    assert isinstance(dc.DEFAULT_CONFIG["parallel_analyst_workers"], int)
    assert dc.DEFAULT_CONFIG["analyst_max_tool_iterations"] == 10
    assert isinstance(dc.DEFAULT_CONFIG["analyst_max_tool_iterations"], int)
    assert dc.DEFAULT_CONFIG["data_tool_cache_ttl_seconds"] == 60
    assert isinstance(dc.DEFAULT_CONFIG["data_tool_cache_ttl_seconds"], int)
    assert dc.DEFAULT_CONFIG["sec_request_timeout"] == 45
    assert isinstance(dc.DEFAULT_CONFIG["sec_request_timeout"], int)
    assert dc.DEFAULT_CONFIG["prefetch_workers"] == 3
    assert isinstance(dc.DEFAULT_CONFIG["prefetch_workers"], int)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
        ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
    ],
)
def test_bool_coercion(monkeypatch, raw, expected):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_CHECKPOINT_ENABLED=raw,
        TRADINGAGENTS_PARALLEL_ANALYSTS=raw,
        TRADINGAGENTS_DATA_TOOL_CACHE_ENABLED=raw,
        TRADINGAGENTS_SEC_USE_GLUETUN=raw,
        TRADINGAGENTS_PREFETCH_DATA_ENABLED=raw,
    )
    assert dc.DEFAULT_CONFIG["checkpoint_enabled"] is expected
    assert dc.DEFAULT_CONFIG["parallel_analysts"] is expected
    assert dc.DEFAULT_CONFIG["data_tool_cache_enabled"] is expected
    assert dc.DEFAULT_CONFIG["sec_use_gluetun"] is expected
    assert dc.DEFAULT_CONFIG["prefetch_data_enabled"] is expected


def test_nested_vendor_override(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_FUNDAMENTAL_DATA_VENDOR="edgar,yfinance",
    )

    assert dc.DEFAULT_CONFIG["data_vendors"]["fundamental_data"] == "edgar,yfinance"


def test_empty_env_value_is_passthrough(monkeypatch):
    """Empty TRADINGAGENTS_* values must not clobber the built-in default."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_PROVIDER="",
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="",
    )
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 1


def test_invalid_int_raises(monkeypatch):
    """Garbage int values should surface a ValueError at import, not silently misconfigure."""
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "not-a-number")
    with pytest.raises(ValueError):
        importlib.reload(default_config_module)
    # Restore module state for subsequent tests in this process
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    importlib.reload(default_config_module)


def test_unknown_env_var_is_ignored(monkeypatch):
    """Env vars outside _ENV_OVERRIDES must not bleed into DEFAULT_CONFIG."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_NONEXISTENT_KEY="oops",
    )
    assert "nonexistent_key" not in dc.DEFAULT_CONFIG


def test_run_profile_applies_before_specific_env_overrides(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_RUN_PROFILE="fast",
        TRADINGAGENTS_DEEP_THINK_LLM="custom-deep",
    )

    assert dc.DEFAULT_CONFIG["run_profile"] == "fast"
    assert dc.DEFAULT_CONFIG["llm_provider"] == "ollama"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "qwen3:8b"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "custom-deep"
    assert dc.DEFAULT_CONFIG["selected_analysts"] == ["market", "fundamentals"]
    assert dc.DEFAULT_CONFIG["parallel_analysts"] is True
    assert dc.DEFAULT_CONFIG["data_tool_cache_enabled"] is True


def test_invalid_run_profile_raises(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_RUN_PROFILE", "turbo")
    with pytest.raises(ValueError, match="Unknown TRADINGAGENTS_RUN_PROFILE"):
        importlib.reload(default_config_module)

    monkeypatch.delenv("TRADINGAGENTS_RUN_PROFILE", raising=False)
    importlib.reload(default_config_module)
