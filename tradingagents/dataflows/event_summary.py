from __future__ import annotations

import re
from typing import Any


EVENT_KEYS = {
    "earnings date": "earnings_date",
    "earnings high": "earnings_high",
    "earnings low": "earnings_low",
    "earnings average": "earnings_average",
    "revenue high": "revenue_high",
    "revenue low": "revenue_low",
    "revenue average": "revenue_average",
    "ex-dividend date": "ex_dividend_date",
    "dividend date": "dividend_date",
}


def build_event_summary_payload(
    *,
    ticker: str,
    curr_date: str,
    event_text: str,
) -> dict[str, Any]:
    facts = _parse_event_lines(event_text)
    return {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "as_of": curr_date,
        "source": _source_label(event_text),
        "parser_status": "parsed" if facts else "unparsed",
        "fact_count": len(facts),
        "events": facts,
        "data_quality_warnings": _build_warnings(facts),
        "raw_excerpt": event_text[:4000] if not facts else None,
    }


def render_event_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"# Deterministic Event Calendar Summary: {payload['ticker']}",
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
                "The event calendar response did not contain parseable line-item facts. Do not invent earnings dates, ex-dividend dates, dividend dates, or investor-day timing.",
                "",
                "```text",
                str(payload.get("raw_excerpt") or "").strip(),
                "```",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Calendar Facts",
            "",
            "| Event | Value | Source |",
            "| --- | --- | --- |",
        ]
    )
    for event in payload["events"].values():
        lines.append(f"| {event['label']} | {event['value']} | {payload['source']} |")

    lines.extend(["", "## Deterministic Guardrails", ""])
    for warning in payload["data_quality_warnings"]:
        lines.append(f"- {warning}")
    lines.append("- Cite calendar dates only from this summary; do not invent event timing when absent.")
    return "\n".join(lines)


def _parse_event_lines(text: str) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for line in (text or "").splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        label, raw_value = [part.strip() for part in line.split(":", 1)]
        metric = EVENT_KEYS.get(_normalize(label))
        if not metric:
            continue
        facts[metric] = {
            "event": metric,
            "label": label,
            "value": raw_value,
            "numeric_value": _parse_number(raw_value),
            "dates": re.findall(r"\d{4}-\d{2}-\d{2}", raw_value),
        }
    return facts


def _build_warnings(facts: dict[str, dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if "earnings_date" not in facts:
        warnings.append("Upcoming earnings date is unavailable; do not cite a next earnings date.")
    if "ex_dividend_date" not in facts:
        warnings.append("Ex-dividend date is unavailable; do not cite an ex-dividend date.")
    warnings.append("Investor days, product launches, and regulatory events are not available in this fact pack unless explicitly listed.")
    return warnings


def _source_label(text: str) -> str:
    if "Source: yfinance calendar" in text:
        return "yfinance calendar"
    return "event calendar vendor"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_number(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.strip().replace(",", "")
    if cleaned.lower() in {"n/a", "na", "none", "nan"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None
