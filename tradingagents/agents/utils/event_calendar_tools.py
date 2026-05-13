from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.agents.utils.artifact_payloads import append_artifact
from tradingagents.dataflows.event_summary import (
    build_event_summary_payload,
    render_event_summary,
)
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_event_calendar_summary(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """Retrieve deterministic upcoming event calendar inputs for a ticker."""
    event_text = route_to_vendor("get_event_calendar", ticker, curr_date)
    payload = build_event_summary_payload(
        ticker=ticker,
        curr_date=curr_date,
        event_text=event_text,
    )
    return append_artifact(render_event_summary(payload), "event_facts", payload)
