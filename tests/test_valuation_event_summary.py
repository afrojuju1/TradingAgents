from __future__ import annotations

from tradingagents.agents.utils import event_calendar_tools, valuation_tools
from tradingagents.dataflows.event_summary import build_event_summary_payload
from tradingagents.dataflows.valuation_summary import build_valuation_summary_payload


VALUATION_TEXT = """# Valuation data for AMD
# Source: yfinance info

Market Cap: 250000000000
Enterprise Value: 248000000000
Trailing PE: 36.5
Forward PE: 28.2
Price to Book: 4.1
Dividend Yield: 0.0125
"""


EVENT_TEXT = """# Event calendar for AMD
# Source: yfinance calendar

Earnings Date: 2026-07-28
Ex-Dividend Date: 2026-06-12
"""


def test_valuation_summary_parses_supported_fields():
    payload = build_valuation_summary_payload(
        ticker="AMD",
        curr_date="2026-05-12",
        valuation_text=VALUATION_TEXT,
    )

    assert payload["parser_status"] == "parsed"
    assert payload["facts"]["market_cap"]["numeric_value"] == 250_000_000_000
    assert payload["facts"]["dividend_yield"]["unit"] == "ratio"


def test_event_summary_parses_calendar_dates():
    payload = build_event_summary_payload(
        ticker="AMD",
        curr_date="2026-05-12",
        event_text=EVENT_TEXT,
    )

    assert payload["parser_status"] == "parsed"
    assert payload["events"]["earnings_date"]["dates"] == ["2026-07-28"]
    assert payload["events"]["ex_dividend_date"]["value"] == "2026-06-12"


def test_valuation_and_event_tools_use_routes(monkeypatch):
    calls = []

    def fake_route(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        if method == "get_valuation":
            return VALUATION_TEXT
        return EVENT_TEXT

    monkeypatch.setattr(valuation_tools, "route_to_vendor", fake_route)
    monkeypatch.setattr(event_calendar_tools, "route_to_vendor", fake_route)

    valuation = valuation_tools.get_valuation_summary.invoke(
        {"ticker": "AMD", "curr_date": "2026-05-12"}
    )
    events = event_calendar_tools.get_event_calendar_summary.invoke(
        {"ticker": "AMD", "curr_date": "2026-05-12"}
    )

    assert "Deterministic Valuation Summary: AMD" in valuation
    assert "Deterministic Event Calendar Summary: AMD" in events
    assert calls == [
        ("get_valuation", ("AMD", "2026-05-12"), {}),
        ("get_event_calendar", ("AMD", "2026-05-12"), {}),
    ]
