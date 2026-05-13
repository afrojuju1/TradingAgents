"""Tests for optional vendor tool-result caching."""

from __future__ import annotations

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import tradingagents.default_config as default_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config


def _configure_cache(tmp_path, *, enabled: bool, category: str = "core_stock_apis"):
    config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config["data_cache_dir"] = str(tmp_path)
    config["data_tool_cache_enabled"] = enabled
    config["data_tool_cache_ttl_seconds"] = 3600
    config["data_vendors"][category] = "dummy"
    set_config(config)
    interface._CACHE_LOCKS.clear()


def test_route_to_vendor_uses_cache_when_enabled(tmp_path, monkeypatch):
    _configure_cache(tmp_path, enabled=True)
    calls = 0

    def impl(symbol, start_date, end_date):
        nonlocal calls
        calls += 1
        return f"{symbol}:{start_date}:{end_date}"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "dummy", impl)

    first = interface.route_to_vendor("get_stock_data", "AMD", "2026-05-01", "2026-05-12")
    second = interface.route_to_vendor("get_stock_data", "AMD", "2026-05-01", "2026-05-12")

    assert first == "AMD:2026-05-01:2026-05-12"
    assert second == first
    assert calls == 1


def test_route_to_vendor_skips_cache_when_disabled(tmp_path, monkeypatch):
    _configure_cache(tmp_path, enabled=False)
    calls = 0

    def impl(symbol, start_date, end_date):
        nonlocal calls
        calls += 1
        return f"call {calls}"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "dummy", impl)

    assert interface.route_to_vendor("get_stock_data", "AMD", "2026-05-01", "2026-05-12") == "call 1"
    assert interface.route_to_vendor("get_stock_data", "AMD", "2026-05-01", "2026-05-12") == "call 2"


def test_route_to_vendor_does_not_cache_error_strings(tmp_path, monkeypatch):
    _configure_cache(tmp_path, enabled=True, category="news_data")
    calls = 0

    def impl(ticker, start_date, end_date):
        nonlocal calls
        calls += 1
        return f"Error fetching news for {ticker}: temporary failure {calls}"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "dummy", impl)

    first = interface.route_to_vendor("get_news", "AMD", "2026-05-01", "2026-05-12")
    second = interface.route_to_vendor("get_news", "AMD", "2026-05-01", "2026-05-12")

    assert first.endswith("temporary failure 1")
    assert second.endswith("temporary failure 2")


def test_route_to_vendor_deduplicates_concurrent_cache_misses(tmp_path, monkeypatch):
    _configure_cache(tmp_path, enabled=True)
    calls = 0
    calls_lock = threading.Lock()

    def impl(symbol, start_date, end_date):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return f"{symbol}:{start_date}:{end_date}"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_stock_data"], "dummy", impl)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: interface.route_to_vendor(
                    "get_stock_data",
                    "AMD",
                    "2026-05-01",
                    "2026-05-12",
                ),
                range(2),
            )
        )

    assert results == [
        "AMD:2026-05-01:2026-05-12",
        "AMD:2026-05-01:2026-05-12",
    ]
    assert calls == 1
