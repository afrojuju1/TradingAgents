from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.agents.utils.artifact_payloads import append_artifact
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.market_summary import (
    DEFAULT_MARKET_INDICATORS,
    build_market_summary_payload,
    render_market_summary,
)


@tool
def get_market_summary(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many calendar days to look back"] = 365,
) -> str:
    """
    Retrieve a deterministic technical market summary for a ticker.

    The summary parses raw OHLCV and indicator outputs into normalized facts so
    analysts do not need to infer prices, ranges, RSI, MACD, or moving averages
    from raw CSV/tool text.
    """
    days = max(30, min(int(look_back_days), 1095))
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d").date()
    start_date = (curr_dt - timedelta(days=days)).isoformat()
    end_date = (curr_dt + timedelta(days=1)).isoformat()

    stock_data_text = route_to_vendor("get_stock_data", symbol, start_date, end_date)
    indicator_texts = {
        indicator: route_to_vendor("get_indicators", symbol, indicator, curr_date, 30)
        for indicator in DEFAULT_MARKET_INDICATORS
    }
    payload = build_market_summary_payload(
        symbol=symbol,
        curr_date=curr_date,
        stock_data_text=stock_data_text,
        indicator_texts=indicator_texts,
    )
    return append_artifact(render_market_summary(payload), "market_facts", payload)
