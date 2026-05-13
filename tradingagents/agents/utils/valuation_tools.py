from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.agents.utils.artifact_payloads import append_artifact
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.valuation_summary import (
    build_valuation_summary_payload,
    render_valuation_summary,
)


@tool
def get_valuation_summary(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve deterministic market valuation inputs for a ticker."""
    valuation_text = route_to_vendor("get_valuation", ticker, curr_date)
    payload = build_valuation_summary_payload(
        ticker=ticker,
        curr_date=curr_date,
        valuation_text=valuation_text,
    )
    return append_artifact(render_valuation_summary(payload), "valuation_facts", payload)
