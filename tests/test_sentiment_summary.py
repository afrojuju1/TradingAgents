from __future__ import annotations

from tradingagents.dataflows.sentiment_summary import (
    build_sentiment_summary_payload,
    render_sentiment_summary,
)


def test_sentiment_summary_extracts_stocktwits_and_reddit_counts():
    payload = build_sentiment_summary_payload(
        ticker="AMD",
        start_date="2026-05-05",
        end_date="2026-05-12",
        news_block="",
        stocktwits_block=(
            "Bullish: 7 (70%) - Bearish: 2 (20%) - Unlabeled: 1 - Total: 10 most-recent messages\n"
            "[2026-05-12T00:00:00Z - @u - Bullish] test"
        ),
        reddit_block=(
            "r/stocks - 2 recent posts mentioning AMD:\n"
            "  [2026-05-12 -   42 up -  10c] AMD thread\n"
            "  [2026-05-11 -    5 up -   2c] Another AMD thread"
        ),
    )

    assert payload["stocktwits"]["bullish"] == 7
    assert payload["stocktwits"]["bullish_share_pct"] == 70
    assert payload["reddit"]["total_posts"] == 2
    assert payload["reddit"]["total_score"] == 47
    assert payload["reddit"]["total_comments"] == 12


def test_render_sentiment_summary_contains_guardrails():
    payload = build_sentiment_summary_payload(
        ticker="AMD",
        start_date="2026-05-05",
        end_date="2026-05-12",
        news_block="",
        stocktwits_block="<stocktwits unavailable: HTTPError>",
        reddit_block="<no Reddit posts found mentioning AMD across r/stocks in the past 7 days>",
    )

    rendered = render_sentiment_summary(payload)

    assert "Deterministic Sentiment Fact Summary: AMD" in rendered
    assert "small sample" in rendered
    assert "Do not infer broad retail consensus" in rendered
