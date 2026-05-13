from __future__ import annotations

from tradingagents.dataflows.news_summary import (
    build_news_summary_payload,
    render_news_summary,
)


COMPANY_NEWS = """## JPM News, from 2026-05-05 to 2026-05-12:

### JPMorgan expands tokenized collateral pilot (source: Reuters)
Published: 2026-05-10
JPMorgan said it expanded a tokenized collateral pilot for institutional clients.
Link: https://example.com/jpm-tokenized
"""


GLOBAL_NEWS = """## Global Market News, from 2026-05-05 to 2026-05-12:

### Fed officials debate rates as inflation cools (source: MarketWatch)
Published: 2026-05-11
Federal Reserve officials discussed rates and inflation risks.
Link: https://example.com/fed-rates

### Shoe retailer launches new store format (source: Example)
Published: 2026-05-10
Retail store design update with no macro relevance.
"""


def test_news_summary_extracts_sources_and_scores_relevance():
    payload = build_news_summary_payload(
        ticker="JPM",
        curr_date="2026-05-12",
        company_news_text=COMPANY_NEWS,
        global_news_text=GLOBAL_NEWS,
    )

    assert payload["source_count"] == 3
    assert payload["sources"][0]["source_id"].startswith("news:")
    assert any(source["publisher"] == "Reuters" for source in payload["sources"])
    assert any(source["relevance_score"] < 0.4 for source in payload["sources"])


def test_render_news_summary_requires_source_ids_for_claims():
    payload = build_news_summary_payload(
        ticker="JPM",
        curr_date="2026-05-12",
        company_news_text=COMPANY_NEWS,
        global_news_text=GLOBAL_NEWS,
    )

    rendered = render_news_summary(payload)

    assert "news:company:001" in rendered
    assert "Cite source IDs" in rendered
