from __future__ import annotations

import re
from typing import Any


VALUATION_KEYS = {
    "market cap": "market_cap",
    "enterprise value": "enterprise_value",
    "trailing pe": "trailing_pe",
    "forward pe": "forward_pe",
    "price to book": "price_to_book",
    "dividend yield": "dividend_yield",
    "beta": "beta",
    "52 week high": "fifty_two_week_high",
    "52 week low": "fifty_two_week_low",
    "50 day average": "fifty_day_average",
    "200 day average": "two_hundred_day_average",
}


MONEY_METRICS = {
    "market_cap",
    "enterprise_value",
    "fifty_two_week_high",
    "fifty_two_week_low",
    "fifty_day_average",
    "two_hundred_day_average",
}


PERCENT_METRICS = {"dividend_yield"}


def build_valuation_summary_payload(
    *,
    ticker: str,
    curr_date: str,
    valuation_text: str,
) -> dict[str, Any]:
    facts = _parse_valuation_lines(valuation_text)
    return {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "as_of": curr_date,
        "source": _source_label(valuation_text),
        "parser_status": "parsed" if facts else "unparsed",
        "fact_count": len(facts),
        "facts": facts,
        "data_quality_warnings": _build_warnings(facts),
        "raw_excerpt": valuation_text[:4000] if not facts else None,
    }


def render_valuation_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"# Deterministic Valuation Summary: {payload['ticker']}",
        "",
        f"Source: {payload['source']}",
        f"Facts available as of trading date: {payload['as_of']}",
        f"Parser status: {payload['parser_status']} ({payload['fact_count']} facts)",
        "",
    ]

    if payload["parser_status"] != "parsed":
        lines.extend(
            [
                "## Parser Notice",
                "",
                "The valuation response did not contain parseable line-item facts. Do not invent market cap, enterprise value, P/E, price/book, or dividend yield.",
                "",
                "```text",
                str(payload.get("raw_excerpt") or "").strip(),
                "```",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Valuation Facts",
            "",
            "| Metric | Value | Normalized | Source |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for fact in payload["facts"].values():
        lines.append(
            f"| {fact['label']} | {fact['value']} | {_render_value(fact)} | {payload['source']} |"
        )

    lines.extend(["", "## Deterministic Guardrails", ""])
    for warning in payload["data_quality_warnings"]:
        lines.append(f"- {warning}")
    lines.extend(
        [
            "- Cite valuation fields only from this summary; do not invent price targets, peer medians, or buyback yield when absent.",
            "- Dividend yield is rendered as a percentage when the source supplies a fractional yield.",
        ]
    )
    return "\n".join(lines)


def _parse_valuation_lines(text: str) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for line in (text or "").splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        label, raw_value = [part.strip() for part in line.split(":", 1)]
        metric = VALUATION_KEYS.get(_normalize(label))
        if not metric:
            continue
        numeric_value = _parse_number(raw_value)
        facts[metric] = {
            "metric": metric,
            "label": label,
            "value": raw_value,
            "numeric_value": numeric_value,
            "unit": _unit_for_metric(metric),
        }
    return facts


def _build_warnings(facts: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if "market_cap" not in facts:
        warnings.append("Market cap is unavailable; do not cite market capitalization.")
    if "enterprise_value" not in facts:
        warnings.append("Enterprise value is unavailable; do not cite EV-based metrics.")
    if "dividend_yield" not in facts:
        warnings.append("Dividend yield is unavailable; do not cite dividend yield.")
    if "trailing_pe" not in facts and "forward_pe" not in facts:
        warnings.append("P/E valuation is unavailable; do not cite trailing or forward P/E.")
    warnings.append("Sector peer medians and buyback yield are not available in this fact pack unless explicitly listed.")
    return warnings


def _source_label(text: str) -> str:
    if "Source: yfinance info" in text:
        return "yfinance info"
    return "valuation vendor"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_number(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.strip().replace(",", "")
    if cleaned.lower() in {"n/a", "na", "none", "nan"}:
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


def _unit_for_metric(metric: str) -> str:
    if metric in MONEY_METRICS:
        return "usd"
    if metric in PERCENT_METRICS:
        return "ratio"
    return "multiple"


def _render_value(fact: dict[str, Any]) -> str:
    value = fact.get("numeric_value")
    if not isinstance(value, (int, float)):
        return "N/A"
    metric = fact.get("metric")
    if metric in MONEY_METRICS:
        return _fmt_money(value)
    if metric in PERCENT_METRICS:
        return f"{float(value) * 100:.2f}%"
    return f"{float(value):,.2f}"


def _fmt_money(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.2f}"
