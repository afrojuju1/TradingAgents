import hashlib
import json
import os
import tempfile
import threading
import time
from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "yfinance",
    "alpha_vantage",
]

_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")


def _tool_cache_enabled(config: dict) -> bool:
    return bool(config.get("data_tool_cache_enabled", False))


def _tool_cache_key(method: str, vendor: str, args: tuple, kwargs: dict) -> str:
    payload = {
        "method": method,
        "vendor": vendor,
        "args": args,
        "kwargs": kwargs,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tool_cache_path(config: dict, method: str, vendor: str, cache_key: str) -> str:
    return os.path.join(
        config["data_cache_dir"],
        "tool_results",
        method,
        vendor,
        f"{cache_key}.json",
    )


def _cache_lock(cache_key: str) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        lock = _CACHE_LOCKS.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _CACHE_LOCKS[cache_key] = lock
        return lock


def _read_tool_cache(config: dict, method: str, vendor: str, cache_key: str):
    path = _tool_cache_path(config, method, vendor, cache_key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    ttl_seconds = int(config.get("data_tool_cache_ttl_seconds", 0))
    created_at = float(payload.get("created_at", 0))
    if ttl_seconds > 0 and time.time() - created_at > ttl_seconds:
        return None

    return payload.get("result")


def _is_cacheable_result(result) -> bool:
    if isinstance(result, str) and result.lstrip().lower().startswith("error "):
        return False
    return True


def _write_tool_cache(
    config: dict,
    method: str,
    vendor: str,
    cache_key: str,
    result,
) -> None:
    if not _is_cacheable_result(result):
        return

    path = _tool_cache_path(config, method, vendor, cache_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "created_at": time.time(),
        "method": method,
        "vendor": vendor,
        "result": result,
    }

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=os.path.dirname(path),
            delete=False,
        ) as handle:
            tmp_path = handle.name
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp_path, path)
    except (OSError, TypeError):
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _call_vendor_with_cache(
    config: dict,
    method: str,
    vendor: str,
    impl_func,
    args: tuple,
    kwargs: dict,
):
    if not _tool_cache_enabled(config):
        return impl_func(*args, **kwargs)

    cache_key = _tool_cache_key(method, vendor, args, kwargs)
    cached_result = _read_tool_cache(config, method, vendor, cache_key)
    if cached_result is not None:
        return cached_result

    with _cache_lock(cache_key):
        cached_result = _read_tool_cache(config, method, vendor, cache_key)
        if cached_result is not None:
            return cached_result

        result = impl_func(*args, **kwargs)
        _write_tool_cache(config, method, vendor, cache_key, result)
        return result


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    config = get_config()
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return _call_vendor_with_cache(
                config,
                method,
                vendor,
                impl_func,
                args,
                kwargs,
            )
        except AlphaVantageRateLimitError:
            continue  # Only rate limits trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")
