from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Optional

from langchain_core.tools import tool

from tradingagents.agents.utils.artifact_payloads import append_artifact
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.news_summary import (
    build_news_summary_payload,
    render_news_summary,
)


@tool
def get_news_summary(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    look_back_days: Annotated[Optional[int], "days to look back"] = None,
    limit: Annotated[Optional[int], "max global articles"] = None,
) -> str:
    """
    Retrieve a deterministic news source summary for company and global news.
    """
    days = 7 if look_back_days is None else max(1, int(look_back_days))
    end = datetime.strptime(curr_date, "%Y-%m-%d").date()
    start = (end - timedelta(days=days)).isoformat()
    company_news_text = route_to_vendor("get_news", ticker, start, curr_date)
    global_news_text = route_to_vendor("get_global_news", curr_date, days, limit)
    payload = build_news_summary_payload(
        ticker=ticker,
        curr_date=curr_date,
        company_news_text=company_news_text,
        global_news_text=global_news_text,
    )
    return append_artifact(render_news_summary(payload), "news_sources", payload)
