from __future__ import annotations

from tradingagents.dataflows import prefetch


def test_build_prefetch_tasks_for_full_analyst_set():
    tasks = prefetch.build_prefetch_tasks(
        "OXY",
        "2026-05-13",
        ["market", "social", "news", "fundamentals"],
        {
            "global_news_lookback_days": 7,
            "global_news_article_limit": 10,
        },
    )

    methods = [task.method for task in tasks]

    assert methods.count("get_stock_data") == 1
    assert methods.count("get_indicators") == len(prefetch.COMMON_PREFETCH_INDICATORS)
    assert "get_fundamentals" in methods
    assert "get_balance_sheet" not in methods
    assert "get_cashflow" not in methods
    assert "get_income_statement" not in methods
    assert "get_news" in methods
    assert "get_global_news" in methods
    assert "get_insider_transactions" in methods


def test_prefetch_skips_when_cache_disabled(monkeypatch):
    calls = 0

    def fail_if_called(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("route_to_vendor should not be called")

    monkeypatch.setattr(prefetch, "route_to_vendor", fail_if_called)

    results = prefetch.prefetch_data(
        "OXY",
        "2026-05-13",
        ["fundamentals"],
        {
            "prefetch_data_enabled": True,
            "data_tool_cache_enabled": False,
        },
    )

    assert results == []
    assert calls == 0
