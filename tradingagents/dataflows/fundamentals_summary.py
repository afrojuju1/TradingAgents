from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


BANK_OR_FINANCIAL_TICKERS = {
    "JPM",
    "BAC",
    "C",
    "WFC",
    "GS",
    "MS",
    "USB",
    "PNC",
    "TFC",
    "COF",
    "BK",
    "STT",
    "SCHW",
    "AXP",
    "BLK",
}

METRIC_KEYS = {
    "cash and equivalents": "cash_and_equivalents",
    "current assets": "current_assets",
    "current liabilities": "current_liabilities",
    "total assets": "total_assets",
    "total liabilities": "total_liabilities",
    "stockholders' equity": "stockholders_equity",
    "stockholders equity": "stockholders_equity",
    "short-term debt": "short_term_debt",
    "current debt": "current_debt",
    "long-term debt": "long_term_debt",
    "long-term debt incl. current maturities": "long_term_debt_including_current",
    "total debt": "total_debt",
    "net debt": "net_debt",
    "debt to equity": "debt_to_equity",
    "current ratio": "current_ratio",
    "revenue": "revenue",
    "gross profit": "gross_profit",
    "operating income": "operating_income",
    "pretax income": "pretax_income",
    "net income": "net_income",
    "diluted eps": "diluted_eps",
    "operating cash flow": "operating_cash_flow",
    "capital expenditures": "capital_expenditures",
    "dividends paid": "dividends_paid",
    "share repurchases": "share_repurchases",
    "free cash flow": "free_cash_flow",
}

BALANCE_METRICS = (
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "cash_and_equivalents",
    "total_debt",
    "net_debt",
    "debt_to_equity",
    "current_ratio",
)

INCOME_CASH_FLOW_METRICS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "diluted_eps",
    "operating_cash_flow",
    "capital_expenditures",
    "free_cash_flow",
    "dividends_paid",
    "share_repurchases",
)


@dataclass(frozen=True)
class FundamentalFact:
    metric: str
    label: str
    value: str
    numeric_value: float | None
    section: str
    period: str | None
    period_end: str | None
    filing_date: str | None
    form: str | None
    accession: str | None
    concept: str | None
    components: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "label": self.label,
            "value": self.value,
            "numeric_value": self.numeric_value,
            "section": self.section,
            "period": self.period,
            "period_end": self.period_end,
            "filing_date": self.filing_date,
            "form": self.form,
            "accession": self.accession,
            "concept": self.concept,
            "components": self.components,
        }


def parse_fundamental_facts(text: str) -> list[FundamentalFact]:
    """Parse SEC markdown tables emitted by the fundamentals vendor."""
    if not text:
        return []

    section = "Header"
    facts: list[FundamentalFact] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("## "):
            section = line[3:].strip()
            index += 1
            continue

        if not _is_table_line(line):
            index += 1
            continue

        table_lines: list[str] = []
        while index < len(lines) and _is_table_line(lines[index].strip()):
            table_lines.append(lines[index].strip())
            index += 1
        facts.extend(_parse_table(table_lines, section))

    return facts


def build_fundamentals_summary_payload(
    *,
    ticker: str,
    curr_date: str,
    fundamentals_text: str,
) -> dict[str, Any]:
    facts = parse_fundamental_facts(fundamentals_text)
    by_metric = _best_fact_by_metric(facts)
    relationships = _derive_relationships(by_metric)
    context = _classify_accounting_context(ticker, by_metric, fundamentals_text)
    warnings = _build_guardrails(context, by_metric, relationships, fundamentals_text)

    return {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "as_of": curr_date,
        "source": _source_label(fundamentals_text),
        "parser_status": "parsed" if facts else "unparsed",
        "fact_count": len(facts),
        "accounting_context": context,
        "relationships": relationships,
        "facts": {metric: fact.to_dict() for metric, fact in by_metric.items()},
        "data_quality_warnings": warnings,
        "raw_excerpt": fundamentals_text[:4000] if not facts else None,
    }


def render_fundamentals_summary(payload: dict[str, Any]) -> str:
    context = payload["accounting_context"]
    relationships = payload["relationships"]
    facts = payload["facts"]

    lines = [
        f"# Deterministic Fundamentals Summary: {payload['ticker']}",
        "",
        (
            f"# Source: {payload['source']}"
            if payload["source"] == "SEC EDGAR via edgartools"
            else f"Source: {payload['source']}"
        ),
        f"Facts available as of trading date: {payload['as_of']}",
        f"Parser status: {payload['parser_status']} ({payload['fact_count']} facts)",
        "",
    ]

    if payload["parser_status"] != "parsed":
        lines.extend(
            [
                "## Parser Notice",
                "",
                "The fundamentals response did not contain parseable SEC-style tables. Treat the excerpt as lower-confidence fallback context and do not invent missing periods, accessions, or source concepts.",
                "",
                "```text",
                str(payload.get("raw_excerpt") or "").strip(),
                "```",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Accounting Context",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Classification | {context['classification']} |",
            f"| Reason | {context['reason']} |",
            f"| Assets vs liabilities | {_relationship_line(relationships)} |",
            "",
            "## Balance Sheet and Leverage",
            "",
            "| Metric | Value | Period | Source |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for metric in BALANCE_METRICS:
        if metric in facts:
            lines.append(_fact_row(facts[metric]))

    lines.extend(
        [
            "",
            "## Income and Cash Flow",
            "",
            "| Metric | Value | Period | Source |",
            "| --- | ---: | --- | --- |",
        ]
    )
    for metric in INCOME_CASH_FLOW_METRICS:
        if metric in facts:
            lines.append(_fact_row(facts[metric]))

    lines.extend(["", "## Deterministic Guardrails", ""])
    for warning in payload["data_quality_warnings"]:
        lines.append(f"- {warning}")
    lines.extend(
        [
            "- Preserve period end, filing date, form, accession, and concept when citing SEC-derived values.",
            "- Do not introduce market valuation fields, AUM figures, price targets, or macro numbers unless another tool supplied them.",
            "- This summary is analysis input only and is not a BUY/HOLD/SELL portfolio decision.",
        ]
    )
    return "\n".join(lines)


def build_fundamentals_summary(
    *,
    ticker: str,
    curr_date: str,
    fundamentals_text: str,
) -> str:
    payload = build_fundamentals_summary_payload(
        ticker=ticker,
        curr_date=curr_date,
        fundamentals_text=fundamentals_text,
    )
    return render_fundamentals_summary(payload)


def _is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _parse_table(table_lines: list[str], section: str) -> list[FundamentalFact]:
    if len(table_lines) < 3:
        return []

    headers = [_clean_cell(cell) for cell in table_lines[0].strip("|").split("|")]
    lower_headers = [_normalise_label(header) for header in headers]
    if "metric" not in lower_headers or "value" not in lower_headers:
        return []

    separator_index = 1
    rows = table_lines[separator_index + 1 :]
    facts: list[FundamentalFact] = []
    for row_line in rows:
        cells = [_clean_cell(cell) for cell in row_line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        row = {lower_headers[i]: cells[i] for i in range(len(headers))}
        label = row.get("metric", "")
        metric = METRIC_KEYS.get(_normalise_label(label))
        if not metric:
            continue

        period = row.get("period") or row.get("period end")
        period_end = row.get("period end") or _extract_period_end(period)
        facts.append(
            FundamentalFact(
                metric=metric,
                label=label,
                value=row.get("value", ""),
                numeric_value=_parse_number(row.get("value")),
                section=section,
                period=period,
                period_end=period_end,
                filing_date=row.get("filing date") or None,
                form=row.get("form") or None,
                accession=row.get("accession") or None,
                concept=row.get("concept") or row.get("source concepts") or None,
                components=row.get("components") or None,
            )
        )
    return facts


def _best_fact_by_metric(facts: list[FundamentalFact]) -> dict[str, FundamentalFact]:
    by_metric: dict[str, FundamentalFact] = {}
    for fact in facts:
        current = by_metric.get(fact.metric)
        if current is None or _fact_priority(fact) > _fact_priority(current):
            by_metric[fact.metric] = fact
    return by_metric


def _fact_priority(fact: FundamentalFact) -> tuple[int, str, str]:
    derived_score = 1 if fact.section.lower().startswith("derived") else 0
    return (
        derived_score,
        fact.period_end or "",
        fact.filing_date or "",
    )


def _derive_relationships(facts: dict[str, FundamentalFact]) -> dict[str, Any]:
    assets = _value(facts, "total_assets")
    liabilities = _value(facts, "total_liabilities")
    equity = _value(facts, "stockholders_equity")
    relationships: dict[str, Any] = {}
    if assets is not None and liabilities is not None:
        relationships["assets_minus_liabilities"] = round(assets - liabilities, 4)
        relationships["liabilities_to_assets"] = (
            round(liabilities / assets, 6) if assets else None
        )
        relationships["assets_greater_than_liabilities"] = assets > liabilities
    if assets is not None and equity is not None:
        relationships["equity_to_assets"] = round(equity / assets, 6) if assets else None
    return relationships


def _classify_accounting_context(
    ticker: str,
    facts: dict[str, FundamentalFact],
    text: str,
) -> dict[str, str]:
    ticker_upper = ticker.upper()
    relationships = _derive_relationships(facts)
    liabilities_to_assets = relationships.get("liabilities_to_assets")
    assets = _value(facts, "total_assets")
    text_l = text.lower()

    if ticker_upper in BANK_OR_FINANCIAL_TICKERS:
        return {
            "classification": "bank_or_financial",
            "reason": f"{ticker_upper} is in the configured bank/financial ticker set.",
        }
    if (
        assets is not None
        and assets >= 50_000_000_000
        and liabilities_to_assets is not None
        and liabilities_to_assets >= 0.80
        and "current ratio" not in text_l
    ):
        return {
            "classification": "bank_or_financial",
            "reason": "Large balance sheet with liabilities/assets above 80% and no current-ratio fact resembles financial-company reporting.",
        }
    return {
        "classification": "general_corporate",
        "reason": "No bank/financial heuristic matched; use standard corporate liquidity and cash-flow interpretation.",
    }


def _build_guardrails(
    context: dict[str, str],
    facts: dict[str, FundamentalFact],
    relationships: dict[str, Any],
    text: str,
) -> list[str]:
    warnings: list[str] = []
    if context["classification"] == "bank_or_financial":
        warnings.extend(
            [
                "Bank/financial context: do not treat negative operating cash flow as standalone evidence of distress or aggressive accounting.",
                "Bank/financial context: deposit, funding, loan, and securities balance-sheet flows can make cash-flow statements volatile and not directly comparable to industrial free cash flow.",
                "Bank/financial context: debt-to-equity and current-ratio style metrics require sector context and should not be benchmarked like an industrial company.",
            ]
        )

    if relationships.get("assets_greater_than_liabilities") is True:
        spread = relationships.get("assets_minus_liabilities")
        warnings.append(
            f"Total assets exceed total liabilities by {_fmt_money(spread)}; do not state that liabilities exceed assets."
        )
    elif relationships.get("assets_greater_than_liabilities") is False:
        spread = abs(float(relationships.get("assets_minus_liabilities") or 0))
        warnings.append(
            f"Total liabilities exceed total assets by {_fmt_money(spread)}; flag this explicitly if material."
        )

    ocf = _value(facts, "operating_cash_flow")
    if ocf is not None and ocf < 0 and context["classification"] != "bank_or_financial":
        warnings.append(
            "Operating cash flow is negative; for non-financial companies this needs explicit working-capital or one-time-item context."
        )

    if "## data quality notes" in text.lower():
        warnings.append(
            "The source report contains Data Quality Notes; repeat stale-period warnings near affected metrics."
        )

    return warnings


def _source_label(text: str) -> str:
    if "SEC EDGAR via edgartools" in text:
        return "SEC EDGAR via edgartools"
    if text.lstrip().startswith("# Company Fundamentals"):
        return "fallback fundamentals vendor"
    return "fundamentals vendor"


def _fact_row(fact: dict[str, Any]) -> str:
    period = fact.get("period") or fact.get("period_end") or "N/A"
    source_parts = [
        part
        for part in (
            fact.get("filing_date"),
            fact.get("form"),
            fact.get("accession"),
            fact.get("concept"),
        )
        if part
    ]
    return (
        f"| {fact['label']} | {fact['value']} | {period} | "
        f"{'; '.join(source_parts) or 'N/A'} |"
    )


def _relationship_line(relationships: dict[str, Any]) -> str:
    if "assets_greater_than_liabilities" not in relationships:
        return "N/A"
    diff = relationships.get("assets_minus_liabilities")
    direction = (
        "assets exceed liabilities"
        if relationships["assets_greater_than_liabilities"]
        else "liabilities exceed assets"
    )
    ratios: list[str] = []
    if relationships.get("liabilities_to_assets") is not None:
        ratios.append(
            f"liabilities/assets {relationships['liabilities_to_assets'] * 100:.1f}%"
        )
    if relationships.get("equity_to_assets") is not None:
        ratios.append(f"equity/assets {relationships['equity_to_assets'] * 100:.1f}%")
    return f"{direction} by {_fmt_money(diff)}" + (
        f" ({', '.join(ratios)})" if ratios else ""
    )


def _value(facts: dict[str, FundamentalFact], metric: str) -> float | None:
    fact = facts.get(metric)
    return fact.numeric_value if fact else None


def _clean_cell(value: str) -> str:
    return value.strip().replace("\\|", "|")


def _normalise_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("’", "'"))


def _extract_period_end(period: str | None) -> str | None:
    if not period:
        return None
    matches = re.findall(r"\d{4}-\d{2}-\d{2}", period)
    return matches[-1] if matches else None


def _parse_number(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.strip().replace(",", "")
    if cleaned.lower() in {"n/a", "na", "none"}:
        return None
    sign = -1 if cleaned.startswith("-") else 1
    cleaned = cleaned.lstrip("+-").lstrip("$")
    multiplier = 1.0
    suffix = cleaned[-1:].upper()
    if suffix in {"K", "M", "B", "T"}:
        cleaned = cleaned[:-1]
        multiplier = {
            "K": 1_000.0,
            "M": 1_000_000.0,
            "B": 1_000_000_000.0,
            "T": 1_000_000_000_000.0,
        }[suffix]
    try:
        return sign * float(cleaned) * multiplier
    except ValueError:
        return None


def _fmt_money(value: Any) -> str:
    if value is None:
        return "N/A"
    number = float(value)
    abs_value = abs(number)
    if abs_value >= 1_000_000_000_000:
        return f"${number / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    return f"${number:,.2f}"
