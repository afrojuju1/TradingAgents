from __future__ import annotations

import re
from typing import Any

from tradingagents.dataflows.news_summary import build_news_summary_payload


def build_sentiment_summary_payload(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> dict[str, Any]:
    stocktwits = _parse_stocktwits(stocktwits_block)
    reddit = _parse_reddit(reddit_block)
    news_sources = build_news_summary_payload(
        ticker=ticker,
        curr_date=end_date,
        company_news_text=news_block,
        global_news_text="",
    )
    warnings: list[str] = []
    if stocktwits["total_messages"] < 10:
        warnings.append("StockTwits sample is small; treat retail sentiment as low confidence.")
    if reddit["total_posts"] == 0:
        warnings.append("No Reddit posts were found in the configured finance subreddits.")
    if news_sources["source_count"] == 0:
        warnings.append("No parseable news headlines were available for sentiment context.")

    return {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "window": {"start": start_date, "end": end_date},
        "stocktwits": stocktwits,
        "reddit": reddit,
        "news": {
            "source_count": news_sources["source_count"],
            "sources": news_sources["sources"],
        },
        "warnings": warnings,
    }


def render_sentiment_summary(payload: dict[str, Any]) -> str:
    stocktwits = payload["stocktwits"]
    reddit = payload["reddit"]
    lines = [
        f"# Deterministic Sentiment Fact Summary: {payload['ticker']}",
        "",
        f"Window: {payload['window']['start']} to {payload['window']['end']}",
        "",
        "| Source | Deterministic facts |",
        "| --- | --- |",
        (
            "| StockTwits | "
            f"{stocktwits['bullish']} bullish, {stocktwits['bearish']} bearish, "
            f"{stocktwits['unlabeled']} unlabeled, {stocktwits['total_messages']} total; "
            f"bullish share {stocktwits['bullish_share_pct']}%, bearish share {stocktwits['bearish_share_pct']}% |"
        ),
        (
            "| Reddit | "
            f"{reddit['total_posts']} posts, {reddit['total_score']} total score, "
            f"{reddit['total_comments']} total comments across parsed subreddits |"
        ),
        f"| News | {payload['news']['source_count']} parseable company-news headlines |",
        "",
        "## Sentiment Guardrails",
        "",
    ]
    for warning in payload["warnings"]:
        lines.append(f"- {warning}")
    lines.extend(
        [
            "- Use the deterministic counts above exactly when citing source volume or ratios.",
            "- Do not infer broad retail consensus from a small sample.",
            "- Separate observed sentiment from price prediction.",
        ]
    )
    return "\n".join(lines)


def _parse_stocktwits(text: str) -> dict[str, Any]:
    match = re.search(
        r"Bullish:\s*(?P<bullish>\d+).*?Bearish:\s*(?P<bearish>\d+).*?"
        r"Unlabeled:\s*(?P<unlabeled>\d+).*?Total:\s*(?P<total>\d+)",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return {
            "available": False,
            "bullish": 0,
            "bearish": 0,
            "unlabeled": 0,
            "total_messages": 0,
            "bullish_share_pct": 0,
            "bearish_share_pct": 0,
        }
    bullish = int(match.group("bullish"))
    bearish = int(match.group("bearish"))
    unlabeled = int(match.group("unlabeled"))
    total = int(match.group("total"))
    return {
        "available": True,
        "bullish": bullish,
        "bearish": bearish,
        "unlabeled": unlabeled,
        "total_messages": total,
        "bullish_share_pct": round(100 * bullish / total) if total else 0,
        "bearish_share_pct": round(100 * bearish / total) if total else 0,
    }


def _parse_reddit(text: str) -> dict[str, Any]:
    total_posts = 0
    total_score = 0
    total_comments = 0
    subreddits: dict[str, int] = {}
    for match in re.finditer(
        r"r/(?P<sub>[A-Za-z0-9_]+)\s+[-\u2014]\s+(?P<count>\d+)\s+recent posts",
        text or "",
    ):
        count = int(match.group("count"))
        subreddits[match.group("sub")] = count
        total_posts += count
    for match in re.finditer(
        r"\[\d{4}-\d{2}-\d{2}\s+.\s*(?P<score>-?\d+)[^\d-]+.\s*(?P<comments>\d+)c\]",
        text or "",
    ):
        total_score += int(match.group("score"))
        total_comments += int(match.group("comments"))
    return {
        "available": total_posts > 0,
        "total_posts": total_posts,
        "total_score": total_score,
        "total_comments": total_comments,
        "subreddits": subreddits,
    }
