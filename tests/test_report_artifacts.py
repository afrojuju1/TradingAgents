from __future__ import annotations

import json

from cli.main import save_report_to_disk


def test_save_report_to_disk_writes_fact_artifacts_and_claim_checks(tmp_path):
    final_state = {
        "market_report": "Market report cites deterministic facts.",
        "sentiment_report": "Sentiment report cites deterministic facts.",
        "news_report": "News report cites news:company:001.",
        "fundamentals_report": "# Source: SEC EDGAR via edgartools\nFundamentals report.",
        "investment_debate_state": {},
        "risk_debate_state": {},
        "trader_investment_plan": "",
        "market_facts": {"price": {"latest_close": 10.0}, "indicators": {}},
        "fundamental_facts": {"source": "SEC EDGAR via edgartools", "facts": {}},
        "news_sources": {"sources": [{"source_id": "news:company:001"}]},
        "sentiment_facts": {"stocktwits": {"total_messages": 0}},
    }

    report_path = save_report_to_disk(final_state, "AMD", tmp_path)

    assert report_path == tmp_path / "complete_report.md"
    assert json.loads((tmp_path / "market_facts.json").read_text())["price"]["latest_close"] == 10.0
    assert json.loads((tmp_path / "fundamental_facts.json").read_text())["source"] == "SEC EDGAR via edgartools"
    assert (tmp_path / "news_sources.json").exists()
    assert (tmp_path / "sentiment_facts.json").exists()
    assert (tmp_path / "claim_checks.json").exists()
    assert "claim_checks" in final_state
