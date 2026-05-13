import os

from tradingagents.run_profiles import DEFAULT_ANALYSTS, apply_run_profile

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":         "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":       "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM":      "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL":      "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE":      "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":    "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS":      "max_risk_discuss_rounds",
    "TRADINGAGENTS_CHECKPOINT_ENABLED":   "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER":     "benchmark_ticker",
    "TRADINGAGENTS_PARALLEL_ANALYSTS":    "parallel_analysts",
    "TRADINGAGENTS_PARALLEL_ANALYST_WORKERS": "parallel_analyst_workers",
    "TRADINGAGENTS_ANALYST_MAX_TOOL_ITERATIONS": "analyst_max_tool_iterations",
    "TRADINGAGENTS_DATA_TOOL_CACHE_ENABLED": "data_tool_cache_enabled",
    "TRADINGAGENTS_DATA_TOOL_CACHE_TTL_SECONDS": "data_tool_cache_ttl_seconds",
    "TRADINGAGENTS_SEC_IDENTITY":       "sec_identity",
    "TRADINGAGENTS_SEC_PROXY_URL":      "sec_proxy_url",
    "TRADINGAGENTS_SEC_USE_GLUETUN":    "sec_use_gluetun",
    "TRADINGAGENTS_GLUETUN_ENV_PATH":   "gluetun_env_path",
    "TRADINGAGENTS_SEC_REQUEST_TIMEOUT": "sec_request_timeout",
    "TRADINGAGENTS_PREFETCH_DATA_ENABLED": "prefetch_data_enabled",
    "TRADINGAGENTS_PREFETCH_WORKERS":   "prefetch_workers",
}

_NESTED_ENV_OVERRIDES = {
    "TRADINGAGENTS_FUNDAMENTAL_DATA_VENDOR": ("data_vendors", "fundamental_data"),
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))

    for env_var, (parent_key, child_key) in _NESTED_ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config.setdefault(parent_key, {})[child_key] = raw

    return config


DEFAULT_CONFIG = _apply_env_overrides(apply_run_profile({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "run_profile": None,
    "selected_analysts": list(DEFAULT_ANALYSTS),
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Run analyst report generation concurrently. This improves local Ollama
    # throughput when OLLAMA_NUM_PARALLEL > 1, but remains opt-in so hosted
    # providers with strict rate limits keep the conservative serial flow.
    "parallel_analysts": False,
    "parallel_analyst_workers": 4,
    "analyst_max_tool_iterations": 12,
    # Optional deterministic prefetch warms the vendor tool cache before LLM
    # analysts start. This is disabled by default because some workflows prefer
    # truly on-demand network calls, but local Ollama runs can opt in.
    "prefetch_data_enabled": False,
    "prefetch_workers": 4,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "report_budgets": {},
    # News / data fetching parameters
    # Increase for longer lookback strategies or to broaden macro coverage;
    # decrease to reduce token usage in agent prompts.
    "news_article_limit": 20,             # max articles per ticker (ticker-news)
    "global_news_article_limit": 10,      # max articles for global/macro news
    "global_news_lookback_days": 7,       # macro news lookback window
    # Search queries used by get_global_news for macro headlines. Extend or
    # replace to broaden geographic / sector coverage.
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # Data vendor configuration
    # Optional cache for vendor tool results. Keep disabled by default so live
    # data freshness remains conservative; local Ollama runs can opt in to
    # avoid repeated network calls across retries and repeated ticker runs.
    "data_tool_cache_enabled": False,
    # Positive values expire cached tool results after this many seconds.
    # Values <= 0 keep cache entries until the files are manually removed.
    "data_tool_cache_ttl_seconds": 6 * 60 * 60,
    # SEC/EDGAR settings. `sec_proxy_url` may point at the authenticated local
    # Gluetun HTTP proxy; Dockerized workflows can instead share Gluetun's
    # network namespace and leave the proxy empty.
    "sec_identity": os.getenv("EDGAR_IDENTITY"),
    "sec_proxy_url": None,
    "sec_use_gluetun": False,
    "gluetun_env_path": None,
    "sec_request_timeout": 30,
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "event_data": "yfinance",            # Options: yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Benchmark for alpha calculation in the reflection layer.
    # ``benchmark_ticker`` (when set) overrides the suffix map for all
    # tickers; leave it None to use ``benchmark_map`` for auto-detection
    # based on the ticker's exchange suffix. SPY remains the US default
    # so the reflection label keeps reading "Alpha vs SPY" for US tickers
    # while non-US tickers get their regional index automatically.
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS":  "^NSEI",    # NSE India (Nifty 50)
        ".BO":  "^BSESN",   # BSE India (Sensex)
        ".T":   "^N225",    # Tokyo (Nikkei 225)
        ".HK":  "^HSI",     # Hong Kong (Hang Seng)
        ".L":   "^FTSE",    # London (FTSE 100)
        ".TO":  "^GSPTSE",  # Toronto (TSX Composite)
        ".AX":  "^AXJO",    # Australia (ASX 200)
        "":     "SPY",      # default for US-listed tickers (no suffix)
    },
}, os.getenv("TRADINGAGENTS_RUN_PROFILE")))
