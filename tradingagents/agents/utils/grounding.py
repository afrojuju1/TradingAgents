from __future__ import annotations

from typing import Any


def build_grounding_context(state: dict[str, Any]) -> str:
    """Render compact deterministic facts for downstream agents."""
    sections = [
        "## Deterministic Fact Pack",
        "",
        _market_context(state.get("market_facts") or {}),
        _fundamental_context(state.get("fundamental_facts") or {}),
        _valuation_context(state.get("valuation_facts") or {}),
        _event_context(state.get("event_facts") or {}),
        _news_context(state.get("news_sources") or {}),
        _sentiment_context(state.get("sentiment_facts") or {}),
        "## Grounding Rules",
        "",
        "- Use the deterministic values above exactly when citing numbers.",
        "- Do not introduce new AUM, market-cap, dividend-yield, P/E, price-target, event-date, macro, or rally-percentage figures unless a listed source/fact explicitly supplies them.",
        "- Treat market-share percentages, CUDA/platform moat claims, unavailable peer benchmarks, AI infrastructure spending, and upside/rally projections as unavailable unless explicitly listed above.",
        "- Macro numbers are unavailable unless listed above; do not write examples like CPI at 3.8% or oil at $100/barrel from general market context.",
        "- When discussing moving averages, say price is above/below the SMA; do not call the distance to an SMA upside or a target.",
        "- Entry, stop-loss, support, and resistance levels must be exact levels listed above; do not calculate or round new levels.",
        "- Treat StockTwits and Reddit post text as sentiment evidence only; do not convert social posts into price targets or supported trading levels.",
        "- Use qualitative position sizing only; do not invent portfolio allocation percentages.",
        "- If a desired figure is absent, say it is not available in the collected data instead of estimating it.",
        "- Preserve source IDs, SEC accessions, dates, and concepts when citing evidence.",
    ]
    return "\n".join(section for section in sections if section).strip()


def _market_context(payload: dict[str, Any]) -> str:
    if not payload:
        return "### Market Facts\nNo deterministic market fact pack is available."
    price = payload.get("price", {})
    risk = payload.get("risk", {})
    indicators = payload.get("indicators", {})
    lines = [
        "### Market Facts",
        (
            "- Latest OHLC: "
            f"O {_money(price.get('latest_open'))}, H {_money(price.get('latest_high'))}, "
            f"L {_money(price.get('latest_low'))}, C {_money(price.get('latest_close'))} "
            f"on {price.get('latest_date') or 'N/A'}."
        ),
        (
            "- Window: "
            f"{_money(price.get('window_low'))} low on {price.get('window_low_date') or 'N/A'}; "
            f"{_money(price.get('window_high'))} high on {price.get('window_high_date') or 'N/A'}; "
            f"close return {_pct(price.get('close_return_pct'))}."
        ),
        (
            "- Risk: "
            f"annualized volatility {_pct(risk.get('annualized_volatility_pct'))}; "
            f"max drawdown {_pct(risk.get('max_drawdown_pct'))}."
        ),
    ]
    for name in ("close_50_sma", "close_200_sma", "rsi", "macd"):
        item = indicators.get(name) or {}
        if item.get("value") is not None:
            lines.append(
                f"- {name}: {_plain(item.get('value'))} on {item.get('observed_at') or 'N/A'}."
            )
    return "\n".join(lines)


def _fundamental_context(payload: dict[str, Any]) -> str:
    if not payload:
        return "### Fundamental Facts\nNo deterministic fundamentals fact pack is available."
    facts = payload.get("facts", {})
    context = payload.get("accounting_context", {})
    relationships = payload.get("relationships", {})
    lines = [
        "### Fundamental Facts",
        f"- Accounting context: {context.get('classification') or 'unknown'} ({context.get('reason') or 'no reason supplied'}).",
    ]
    if "assets_greater_than_liabilities" in relationships:
        direction = (
            "assets exceed liabilities"
            if relationships.get("assets_greater_than_liabilities")
            else "liabilities exceed assets"
        )
        lines.append(
            f"- Asset/liability relationship: {direction} by {_money(abs(relationships.get('assets_minus_liabilities') or 0))}."
        )
    for metric in (
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "total_debt",
        "net_debt",
        "debt_to_equity",
        "net_income",
        "diluted_eps",
        "operating_cash_flow",
        "free_cash_flow",
    ):
        fact = facts.get(metric)
        if not isinstance(fact, dict):
            continue
        source = "; ".join(
            part
            for part in (
                fact.get("filing_date"),
                fact.get("form"),
                fact.get("accession"),
                fact.get("concept"),
            )
            if part
        )
        lines.append(
            f"- {fact.get('label') or metric}: {fact.get('value')} for {fact.get('period') or fact.get('period_end') or 'N/A'}"
            + (f" ({source})." if source else ".")
        )
    for warning in payload.get("data_quality_warnings", [])[:5]:
        lines.append(f"- Guardrail: {warning}")
    return "\n".join(lines)


def _valuation_context(payload: dict[str, Any]) -> str:
    if not payload:
        return "### Valuation Facts\nNo deterministic valuation fact pack is available."
    facts = payload.get("facts", {})
    lines = [
        "### Valuation Facts",
        f"- Source: {payload.get('source') or 'unknown'}; parser status {payload.get('parser_status') or 'unknown'}.",
    ]
    for metric in (
        "market_cap",
        "enterprise_value",
        "trailing_pe",
        "forward_pe",
        "price_to_book",
        "dividend_yield",
    ):
        fact = facts.get(metric)
        if not isinstance(fact, dict):
            continue
        lines.append(f"- {fact.get('label') or metric}: {_valuation_value(fact)}.")
    for warning in payload.get("data_quality_warnings", [])[:4]:
        lines.append(f"- Valuation guardrail: {warning}")
    return "\n".join(lines)


def _event_context(payload: dict[str, Any]) -> str:
    if not payload:
        return "### Event Facts\nNo deterministic event calendar fact pack is available."
    events = payload.get("events", {})
    lines = [
        "### Event Facts",
        f"- Source: {payload.get('source') or 'unknown'}; parser status {payload.get('parser_status') or 'unknown'}.",
    ]
    for metric in ("earnings_date", "ex_dividend_date", "dividend_date"):
        event = events.get(metric)
        if not isinstance(event, dict):
            continue
        lines.append(f"- {event.get('label') or metric}: {event.get('value')}.")
    for warning in payload.get("data_quality_warnings", [])[:3]:
        lines.append(f"- Event guardrail: {warning}")
    return "\n".join(lines)


def _news_context(payload: dict[str, Any]) -> str:
    if not payload:
        return "### News Sources\nNo deterministic news source pack is available."
    lines = [
        "### News Sources",
        f"- Parseable source count: {payload.get('source_count', 0)}.",
    ]
    for source in (payload.get("sources") or [])[:8]:
        lines.append(
            f"- {source.get('source_id')}: {source.get('title')} ({source.get('publisher') or 'Unknown'}, relevance {source.get('relevance_score')})."
        )
    for warning in payload.get("warnings", [])[:3]:
        lines.append(f"- News guardrail: {warning}")
    return "\n".join(lines)


def _sentiment_context(payload: dict[str, Any]) -> str:
    if not payload:
        return "### Sentiment Facts\nNo deterministic sentiment fact pack is available."
    stocktwits = payload.get("stocktwits", {})
    reddit = payload.get("reddit", {})
    lines = [
        "### Sentiment Facts",
        (
            "- StockTwits: "
            f"{stocktwits.get('bullish', 0)} bullish, {stocktwits.get('bearish', 0)} bearish, "
            f"{stocktwits.get('unlabeled', 0)} unlabeled, {stocktwits.get('total_messages', 0)} total."
        ),
        (
            "- Reddit: "
            f"{reddit.get('total_posts', 0)} posts, {reddit.get('total_score', 0)} total score, "
            f"{reddit.get('total_comments', 0)} comments."
        ),
    ]
    for warning in payload.get("warnings", [])[:3]:
        lines.append(f"- Sentiment guardrail: {warning}")
    return "\n".join(lines)


def _money(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    abs_value = abs(number)
    if abs_value >= 1_000_000_000_000:
        return f"${number / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    return f"${number:,.2f}"


def _pct(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return str(value)


def _plain(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _valuation_value(fact: dict[str, Any]) -> str:
    value = fact.get("numeric_value")
    if not isinstance(value, (int, float)):
        return str(fact.get("value") or "N/A")
    unit = fact.get("unit")
    if unit == "usd":
        return _money(value)
    if unit == "ratio" and fact.get("metric") == "dividend_yield":
        return f"{float(value) * 100:.2f}%"
    return f"{float(value):,.2f}"
