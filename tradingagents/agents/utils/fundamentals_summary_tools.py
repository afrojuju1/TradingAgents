from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.fundamentals_summary import build_fundamentals_summary
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_fundamentals_summary(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve a deterministic SEC fundamentals summary for a ticker.

    The summary parses vendor fundamentals into normalized balance-sheet,
    income, cash-flow, leverage, liquidity, and accounting-context facts so the
    analyst does not need to reconcile raw statement tables.
    """
    fundamentals_text = route_to_vendor("get_fundamentals", ticker, curr_date)
    return build_fundamentals_summary(
        ticker=ticker,
        curr_date=curr_date,
        fundamentals_text=fundamentals_text,
    )
