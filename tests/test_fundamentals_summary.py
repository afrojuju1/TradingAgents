from __future__ import annotations

from tradingagents.agents.utils import fundamentals_summary_tools
from tradingagents.dataflows.fundamentals_summary import (
    build_fundamentals_summary_payload,
    parse_fundamental_facts,
    render_fundamentals_summary,
)


JPM_SEC_REPORT = """# SEC Fundamentals for JPM
# Source: SEC EDGAR via edgartools
# Facts available as of trading date: 2026-05-12

## Derived Debt And Liquidity

| Metric | Value | Components | Period End | Filing Date | Form | Accession | Source Concepts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Total debt | $516.81B | Short-term debt, Long-term debt incl. current maturities | 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | ShortTermBorrowings+LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities |
| Net debt | $204.67B | Short-term debt, Long-term debt incl. current maturities, Cash and equivalents | 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | total_debt-CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents |
| Debt to equity | 1.44 | Short-term debt, Long-term debt incl. current maturities, Stockholders' equity | 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | total_debt/StockholdersEquity |

## Balance Sheet Snapshot - Period-Consistent (2026-03-31)

| Metric | Value | Period | Filing Date | Form | Accession | Concept |
| --- | --- | --- | --- | --- | --- | --- |
| Cash and equivalents | $312.14B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents |
| Total assets | $4.56T | as of 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | Assets |
| Total liabilities | $4.21T | as of 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | Liabilities |
| Stockholders' equity | $359.00B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | StockholdersEquity |

## Income Statement Snapshot - Period-Consistent (2026-03-31)

| Metric | Value | Period | Filing Date | Form | Accession | Concept |
| --- | --- | --- | --- | --- | --- | --- |
| Revenue | $46.01B | 90D ended 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | Revenues |
| Net income | $14.64B | 90D ended 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | NetIncomeLoss |
| Diluted EPS | $5.07 | 90D ended 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | EarningsPerShareDiluted |

## Cash Flow Snapshot - Period-Consistent (2026-03-31)

| Metric | Value | Period | Filing Date | Form | Accession | Concept |
| --- | --- | --- | --- | --- | --- | --- |
| Operating cash flow | $-211.76B | 90D ended 2026-03-31 | 2026-05-01 | 10-Q | 0001628280-26-029344 | NetCashProvidedByUsedInOperatingActivities |
"""


CAT_SEC_REPORT = """# SEC Fundamentals for CAT
# Source: SEC EDGAR via edgartools
# Facts available as of trading date: 2026-05-12

## Derived Debt And Liquidity

| Metric | Value | Components | Period End | Filing Date | Form | Accession | Source Concepts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Total debt | $36.21B | Short-term debt, Long-term debt | 2025-12-31 | 2026-02-13 | 10-K | 0000018230-26-000008 | ShortTermBorrowings+LongTermDebtNoncurrent |
| Current ratio | 1.35 | Current assets, Current liabilities | 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | AssetsCurrent/LiabilitiesCurrent |

## Balance Sheet Snapshot - Period-Consistent (2026-03-31)

| Metric | Value | Period | Filing Date | Form | Accession | Concept |
| --- | --- | --- | --- | --- | --- | --- |
| Current assets | $48.57B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | AssetsCurrent |
| Current liabilities | $35.90B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | LiabilitiesCurrent |
| Total assets | $95.55B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | Assets |
| Total liabilities | $76.89B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | Liabilities |
| Stockholders' equity | $18.66B | as of 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | StockholdersEquity |

## Cash Flow Snapshot - Period-Consistent (2026-03-31)

| Metric | Value | Period | Filing Date | Form | Accession | Concept |
| --- | --- | --- | --- | --- | --- | --- |
| Operating cash flow | $-1.20B | 90D ended 2026-03-31 | 2026-05-01 | 10-Q | 0000018230-26-000099 | NetCashProvidedByUsedInOperatingActivities |
"""


def test_parse_fundamental_facts_extracts_sec_tables():
    facts = parse_fundamental_facts(JPM_SEC_REPORT)
    metrics = {fact.metric for fact in facts}

    assert "total_assets" in metrics
    assert "total_debt" in metrics
    assert "operating_cash_flow" in metrics
    assert any(fact.accession == "0001628280-26-029344" for fact in facts)


def test_fundamentals_summary_flags_bank_accounting_context():
    payload = build_fundamentals_summary_payload(
        ticker="JPM",
        curr_date="2026-05-12",
        fundamentals_text=JPM_SEC_REPORT,
    )

    assert payload["accounting_context"]["classification"] == "bank_or_financial"
    assert payload["relationships"]["assets_greater_than_liabilities"] is True
    warnings = "\n".join(payload["data_quality_warnings"])
    assert "negative operating cash flow" in warnings
    assert "do not state that liabilities exceed assets" in warnings


def test_fundamentals_summary_keeps_negative_ocf_warning_for_non_financials():
    payload = build_fundamentals_summary_payload(
        ticker="CAT",
        curr_date="2026-05-12",
        fundamentals_text=CAT_SEC_REPORT,
    )

    assert payload["accounting_context"]["classification"] == "general_corporate"
    assert any(
        "Operating cash flow is negative" in warning
        for warning in payload["data_quality_warnings"]
    )


def test_render_fundamentals_summary_contains_guardrails_and_source_metadata():
    payload = build_fundamentals_summary_payload(
        ticker="JPM",
        curr_date="2026-05-12",
        fundamentals_text=JPM_SEC_REPORT,
    )
    rendered = render_fundamentals_summary(payload)

    assert "$4.56T" in rendered
    assert "0001628280-26-029344" in rendered
    assert "Bank/financial context" in rendered
    assert "Do not introduce market valuation fields" in rendered


def test_fundamentals_summary_tool_uses_single_fundamentals_route(monkeypatch):
    calls = []

    def fake_route(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return JPM_SEC_REPORT

    monkeypatch.setattr(fundamentals_summary_tools, "route_to_vendor", fake_route)

    result = fundamentals_summary_tools.get_fundamentals_summary.invoke(
        {"ticker": "JPM", "curr_date": "2026-05-12"}
    )

    assert calls == [("get_fundamentals", ("JPM", "2026-05-12"), {})]
    assert "Deterministic Fundamentals Summary: JPM" in result
