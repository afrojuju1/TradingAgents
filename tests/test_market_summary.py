from __future__ import annotations

import pytest

from tradingagents.dataflows.market_summary import (
    build_market_summary_payload,
    latest_indicator_value,
    parse_stock_data_csv,
    render_market_summary,
)


STOCK_DATA = """# Stock data for JPM from 2025-05-12 to 2026-05-13
# Total records: 4

Date,Open,High,Low,Close,Volume
2025-05-12,254.00,258.00,253.50,255.00,1000000
2026-05-08,301.00,305.00,299.00,303.00,1200000
2026-05-11,305.00,306.00,300.00,301.00,1100000
2026-05-12,300.02,306.06,295.55,304.88,1500000
"""


def test_parse_stock_data_csv_normalizes_comments_and_columns():
    frame = parse_stock_data_csv(STOCK_DATA)

    assert list(frame.columns) == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert frame.iloc[-1]["Close"] == pytest.approx(304.88)
    assert frame["Low"].min() == pytest.approx(253.50)


def test_parse_stock_data_csv_accepts_alpha_vantage_style_columns():
    frame = parse_stock_data_csv(
        """timestamp,open,high,low,close,adjusted_close,volume
2026-05-12,10,12,9,11,11,100
"""
    )

    assert frame.iloc[0]["Date"].isoformat() == "2026-05-12"
    assert frame.iloc[0]["Close"] == pytest.approx(11)


def test_latest_indicator_value_uses_latest_trading_day_at_or_before_date():
    value = latest_indicator_value(
        "rsi",
        """## rsi values
2026-05-13: N/A: Not a trading day (weekend or holiday)
2026-05-12: 48.538951241279825
2026-05-11: 41.1
""",
        "2026-05-13",
    )

    assert value.observed_at == "2026-05-12"
    assert value.value == pytest.approx(48.539)


def test_market_summary_payload_derives_guardrail_facts_without_llm_parsing():
    payload = build_market_summary_payload(
        symbol="jpm",
        curr_date="2026-05-12",
        stock_data_text=STOCK_DATA,
        indicator_texts={
            "close_50_sma": "2026-05-12: 299.5\n",
            "close_200_sma": "2026-05-12: 302.85\n",
            "rsi": "2026-05-12: 48.538951241279825\n",
            "macd": "2026-05-12: 0.743\n",
        },
    )

    assert payload["symbol"] == "JPM"
    assert payload["price"]["latest_close"] == pytest.approx(304.88)
    assert payload["price"]["window_low"] == pytest.approx(253.5)
    assert payload["indicators"]["rsi"]["value"] == pytest.approx(48.539)
    assert "Neutral" in payload["indicator_context"]["rsi"]
    assert "not overbought" in payload["indicator_context"]["rsi"]


def test_render_market_summary_contains_exact_values_and_guardrails():
    payload = build_market_summary_payload(
        symbol="JPM",
        curr_date="2026-05-12",
        stock_data_text=STOCK_DATA,
        indicator_texts={
            "close_50_sma": "2026-05-12: 299.5\n",
            "close_200_sma": "2026-05-12: 302.85\n",
            "rsi": "2026-05-12: 48.538951241279825\n",
            "macd": "2026-05-12: 0.743\n",
        },
    )
    rendered = render_market_summary(payload)

    assert "$304.88" in rendered
    assert "48.54" in rendered
    assert "not overbought or oversold" in rendered
    assert "Use these deterministic market values exactly" in rendered
