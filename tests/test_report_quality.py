from __future__ import annotations

import json
from pathlib import Path

from tradingagents.report_quality import check_report_quality, main


def _write_report(root: Path, fundamentals: str, complete: str | None = None) -> None:
    (root / "1_analysts").mkdir(parents=True)
    (root / "1_analysts" / "fundamentals.md").write_text(fundamentals, encoding="utf-8")
    (root / "complete_report.md").write_text(complete or fundamentals, encoding="utf-8")


def _codes(root: Path, **kwargs) -> set[str]:
    return {issue.code for issue in check_report_quality(root, **kwargs)}


def test_report_quality_accepts_sec_report_without_recommendation(tmp_path):
    _write_report(
        tmp_path,
        "# Fundamentals\n# Source: SEC EDGAR via edgartools\n\nNet income uses 2026-03-31 facts.",
    )

    assert check_report_quality(tmp_path, require_sec=True) == []


def test_report_quality_flags_stale_year_and_recommendation_leakage(tmp_path):
    _write_report(
        tmp_path,
        "\n".join(
            [
                "# Fundamentals",
                "# Source: SEC EDGAR via edgartools",
                "Net income from 2011 leaked into the current report.",
                "## Recommendation",
                "3. **Recommendation:**",
                "Buy.",
            ]
        ),
    )

    assert _codes(tmp_path, require_sec=True) == {
        "stale_year",
        "analyst_recommendation_leakage",
    }


def test_report_quality_requires_sec_source_when_requested(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n\nYFinance fundamentals only.")

    assert "sec_source_missing" in _codes(tmp_path, require_sec=True)


def test_report_quality_accepts_sec_metadata_when_model_summary_omits_marker(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n\nModel summary of SEC fundamentals.")
    (tmp_path / "run_metadata.json").write_text(
        '{"fundamental_vendor": "edgar,yfinance"}',
        encoding="utf-8",
    )

    assert "sec_source_missing" not in _codes(tmp_path, require_sec=True)


def test_report_quality_accepts_sec_fact_artifact_when_summary_omits_marker(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n\nModel summary of deterministic facts.")
    (tmp_path / "fundamental_facts.json").write_text(
        json.dumps({"source": "SEC EDGAR via edgartools", "facts": {}}),
        encoding="utf-8",
    )

    assert "sec_source_missing" not in _codes(tmp_path, require_sec=True)


def test_report_quality_warns_on_missing_sec_facts_without_failing_by_default(tmp_path, capsys):
    _write_report(
        tmp_path,
        "# Fundamentals\n# Source: SEC EDGAR via edgartools\n\nNo SEC facts found.",
    )

    assert main([str(tmp_path), "--require-sec"]) == 0
    output = capsys.readouterr().out
    assert "WARNING missing_sec_facts" in output


def test_report_quality_strict_warnings_returns_nonzero(tmp_path):
    _write_report(
        tmp_path,
        "# Fundamentals\n# Source: SEC EDGAR via edgartools\n\nNo SEC facts found.",
    )

    assert main([str(tmp_path), "--require-sec", "--strict-warnings"]) == 1


def test_report_quality_flags_market_values_not_in_fact_artifact(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n# Source: SEC EDGAR via edgartools\n")
    (tmp_path / "1_analysts" / "market.md").write_text(
        "Latest close was $304.88, RSI was 70, and the window low was $25.86.",
        encoding="utf-8",
    )
    (tmp_path / "market_facts.json").write_text(
        json.dumps(
            {
                "price": {
                    "latest_close": 304.88,
                    "window_low": 251.12,
                    "window_high": 334.16,
                },
                "indicators": {"rsi": {"value": 48.54}, "macd": {"value": 0.74}},
            }
        ),
        encoding="utf-8",
    )

    codes = _codes(tmp_path)

    assert "market_value_mismatch" in codes
    assert "rsi_mismatch" in codes


def test_report_quality_flags_fundamental_relationship_contradictions(tmp_path):
    _write_report(
        tmp_path,
        (
            "# Fundamentals\n# Source: SEC EDGAR via edgartools\n"
            "Total liabilities exceed assets. Negative operating cash flow is a red flag for distress."
        ),
    )
    (tmp_path / "fundamental_facts.json").write_text(
        json.dumps(
            {
                "accounting_context": {"classification": "bank_or_financial"},
                "relationships": {
                    "assets_greater_than_liabilities": True,
                    "assets_minus_liabilities": 364_040_000_000,
                },
                "facts": {
                    "total_assets": {"numeric_value": 4_900_480_000_000},
                    "total_liabilities": {"numeric_value": 4_536_440_000_000},
                    "operating_cash_flow": {"numeric_value": -211_760_000_000},
                },
            }
        ),
        encoding="utf-8",
    )

    codes = _codes(tmp_path)

    assert "asset_liability_contradiction" in codes
    assert "bank_cashflow_misread" in codes


def test_report_quality_allows_valuation_fact_values(tmp_path):
    report_dir = tmp_path
    analysts_dir = report_dir / "1_analysts"
    analysts_dir.mkdir()
    (report_dir / "complete_report.md").write_text("## Report\n", encoding="utf-8")
    (analysts_dir / "fundamentals.md").write_text(
        "Market cap is $250.00B based on the valuation fact pack.",
        encoding="utf-8",
    )
    (report_dir / "fundamental_facts.json").write_text(
        '{"relationships": {}, "accounting_context": {}, "facts": {}}',
        encoding="utf-8",
    )
    (report_dir / "valuation_facts.json").write_text(
        '{"facts": {"market_cap": {"numeric_value": 250000000000}}}',
        encoding="utf-8",
    )

    codes = _codes(report_dir)

    assert "fundamental_value_unverified" not in codes


def test_report_quality_allows_event_fact_values(tmp_path):
    report_dir = tmp_path
    analysts_dir = report_dir / "1_analysts"
    analysts_dir.mkdir()
    (report_dir / "complete_report.md").write_text("## Report\n", encoding="utf-8")
    (analysts_dir / "fundamentals.md").write_text(
        "Revenue Average was $78.98B and EPS high was $1.99.",
        encoding="utf-8",
    )
    (report_dir / "fundamental_facts.json").write_text(
        '{"relationships": {}, "accounting_context": {}, "facts": {}}',
        encoding="utf-8",
    )
    (report_dir / "event_facts.json").write_text(
        '{"events": {"revenue_average": {"numeric_value": 78979992050}, "earnings_high": {"numeric_value": 1.99}}}',
        encoding="utf-8",
    )

    codes = _codes(report_dir)

    assert "fundamental_value_unverified" not in codes


def test_report_quality_does_not_parse_table_label_as_rsi_value(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n# Source: SEC EDGAR via edgartools\n")
    (tmp_path / "1_analysts" / "market.md").write_text(
        "| Momentum | Positive MACD/RSI | Bullish crossover, neutral RSI |\n"
        "| Volatility | 33.78% annualized | High risk |",
        encoding="utf-8",
    )
    (tmp_path / "market_facts.json").write_text(
        json.dumps({"indicators": {"rsi": {"value": 69.26}, "macd": {"value": 7.15}}}),
        encoding="utf-8",
    )

    codes = _codes(tmp_path)

    assert "rsi_mismatch" not in codes


def test_report_quality_does_not_parse_to_as_trillion_suffix(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n# Source: SEC EDGAR via edgartools\n")
    (tmp_path / "1_analysts" / "market.md").write_text(
        "Yearly return moved from $122.97 to $220.78.",
        encoding="utf-8",
    )
    (tmp_path / "market_facts.json").write_text(
        json.dumps({"price": {"first_close": 122.97, "latest_close": 220.78}}),
        encoding="utf-8",
    )

    codes = _codes(tmp_path)

    assert "unsupported_market_money" not in codes
    assert "market_value_mismatch" not in codes
