from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


MACRO_KEYWORDS = (
    "fed",
    "federal reserve",
    "inflation",
    "cpi",
    "rates",
    "tariff",
    "trade",
    "oil",
    "energy",
    "gdp",
    "earnings",
    "sanctions",
    "central bank",
)


@dataclass(frozen=True)
class NewsSourceRecord:
    source_id: str
    source_type: str
    title: str
    publisher: str | None
    url: str | None
    published_at: str | None
    retrieved_at: str
    summary: str | None
    relevance_score: float
    relevance_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "summary": self.summary,
            "relevance_score": self.relevance_score,
            "relevance_reason": self.relevance_reason,
        }


def build_news_summary_payload(
    *,
    ticker: str,
    curr_date: str,
    company_news_text: str,
    global_news_text: str,
) -> dict[str, Any]:
    sources = [
        *_parse_news_block(
            text=company_news_text,
            source_type="company",
            source_prefix="company",
            ticker=ticker,
            curr_date=curr_date,
        ),
        *_parse_news_block(
            text=global_news_text,
            source_type="global",
            source_prefix="global",
            ticker=ticker,
            curr_date=curr_date,
        ),
    ]
    sources = sorted(
        sources,
        key=lambda source: (source.relevance_score, source.published_at or ""),
        reverse=True,
    )

    warnings: list[str] = []
    if not sources:
        warnings.append("No parseable company or global news sources were found.")
    low_relevance = [source for source in sources if source.relevance_score < 0.4]
    if low_relevance:
        warnings.append(
            f"{len(low_relevance)} source(s) are low relevance and should not drive the thesis."
        )

    return {
        "schema_version": 1,
        "ticker": ticker.upper(),
        "as_of": curr_date,
        "source_count": len(sources),
        "sources": [source.to_dict() for source in sources],
        "warnings": warnings,
    }


def render_news_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"# Deterministic News Source Summary: {payload['ticker']}",
        "",
        f"Sources available as of trading date: {payload['as_of']}",
        f"Parseable source count: {payload['source_count']}",
        "",
        "## Sources",
        "",
        "| ID | Type | Relevance | Date | Publisher | Title |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for source in payload["sources"]:
        lines.append(
            "| {source_id} | {source_type} | {relevance_score:.2f} | {published_at} | {publisher} | {title} |".format(
                source_id=source["source_id"],
                source_type=source["source_type"],
                relevance_score=float(source["relevance_score"]),
                published_at=source.get("published_at") or "N/A",
                publisher=_table_cell(source.get("publisher") or "Unknown"),
                title=_table_cell(source.get("title") or "Untitled"),
            )
        )

    lines.extend(["", "## Summaries", ""])
    for source in payload["sources"][:12]:
        summary = source.get("summary") or "No summary provided."
        url = f" URL: {source['url']}" if source.get("url") else ""
        lines.append(
            f"- {source['source_id']}: {source['title']} ({source.get('publisher') or 'Unknown'}). {summary}{url}"
        )

    lines.extend(["", "## Analyst Guardrails", ""])
    for warning in payload["warnings"]:
        lines.append(f"- {warning}")
    lines.extend(
        [
            "- Cite source IDs for every material company or macro news claim.",
            "- Do not introduce CPI, Fed, oil, dividend, AUM, price-target, or market-cap numbers unless they appear in a listed source.",
            "- Treat low-relevance global headlines as context, not primary ticker evidence.",
            "- This summary is analysis input only and is not a BUY/HOLD/SELL portfolio decision.",
        ]
    )
    return "\n".join(lines)


def build_news_summary(
    *,
    ticker: str,
    curr_date: str,
    company_news_text: str,
    global_news_text: str,
) -> str:
    payload = build_news_summary_payload(
        ticker=ticker,
        curr_date=curr_date,
        company_news_text=company_news_text,
        global_news_text=global_news_text,
    )
    return render_news_summary(payload)


def _parse_news_block(
    *,
    text: str,
    source_type: str,
    source_prefix: str,
    ticker: str,
    curr_date: str,
) -> list[NewsSourceRecord]:
    records: list[NewsSourceRecord] = []
    article_blocks = re.split(r"(?m)^###\s+", text or "")
    for block in article_blocks[1:]:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        title, publisher = _parse_heading(lines[0])
        summary_lines: list[str] = []
        url = None
        published_at = None
        for line in lines[1:]:
            if line.lower().startswith("link:"):
                url = line.split(":", 1)[1].strip() or None
            elif line.lower().startswith("published:"):
                published_at = line.split(":", 1)[1].strip()[:10] or None
            else:
                summary_lines.append(line)

        summary = " ".join(summary_lines).strip() or None
        score, reason = _score_relevance(
            source_type=source_type,
            ticker=ticker,
            title=title,
            summary=summary or "",
        )
        source_id = f"news:{source_prefix}:{len(records) + 1:03d}"
        records.append(
            NewsSourceRecord(
                source_id=source_id,
                source_type=source_type,
                title=title,
                publisher=publisher,
                url=url,
                published_at=published_at,
                retrieved_at=_safe_date(curr_date),
                summary=summary,
                relevance_score=score,
                relevance_reason=reason,
            )
        )
    return records


def _parse_heading(line: str) -> tuple[str, str | None]:
    match = re.match(r"(?P<title>.*)\s+\(source:\s*(?P<publisher>.*)\)\s*$", line)
    if not match:
        return line.strip(), None
    return match.group("title").strip(), match.group("publisher").strip() or None


def _score_relevance(
    *,
    source_type: str,
    ticker: str,
    title: str,
    summary: str,
) -> tuple[float, str]:
    text = f"{title} {summary}".lower()
    ticker_l = ticker.lower()
    if ticker_l in text:
        return 0.95, "mentions ticker"
    if source_type == "company":
        return 0.80, "company news feed"
    matched_keywords = [keyword for keyword in MACRO_KEYWORDS if keyword in text]
    if matched_keywords:
        return 0.60, f"macro keyword: {matched_keywords[0]}"
    return 0.25, "broad global headline with no obvious ticker or macro keyword"


def _safe_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return str(value)


def _table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()
