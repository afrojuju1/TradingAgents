from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd


DEFAULT_MARKET_INDICATORS = (
    "close_50_sma",
    "close_200_sma",
    "rsi",
    "macd",
)


@dataclass(frozen=True)
class IndicatorValue:
    name: str
    observed_at: str | None
    value: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observed_at": self.observed_at,
            "value": self.value,
        }


def parse_stock_data_csv(text: str) -> pd.DataFrame:
    """Parse vendor stock-data CSV output into a normalized OHLCV frame."""
    if not text or not text.strip():
        raise ValueError("Stock data response was empty")

    lines = [
        line.lstrip("\ufeff")
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        raise ValueError("Stock data response did not contain CSV rows")

    frame = pd.read_csv(io.StringIO("\n".join(lines)))
    frame = _normalise_stock_columns(frame)

    required = ("Date", "Open", "High", "Low", "Close")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Stock data missing required columns: {', '.join(missing)}")

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.date
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "Volume" not in frame.columns:
        frame["Volume"] = pd.NA

    frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    frame = frame.sort_values("Date").reset_index(drop=True)
    if frame.empty:
        raise ValueError("Stock data response did not contain parseable OHLC rows")

    return frame[["Date", "Open", "High", "Low", "Close", "Volume"]]


def latest_indicator_value(
    name: str,
    text: str,
    curr_date: str | date | None = None,
) -> IndicatorValue:
    """Return the latest parseable indicator value at or before curr_date."""
    as_of = _parse_date(curr_date) if curr_date else None
    latest: tuple[date, float] | None = None
    pattern = re.compile(
        r"^\s*(\d{4}-\d{2}-\d{2})\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*$",
        re.MULTILINE,
    )

    for match in pattern.finditer(text or ""):
        observed_at = _parse_date(match.group(1))
        if as_of and observed_at > as_of:
            continue
        value = float(match.group(2))
        if latest is None or observed_at > latest[0]:
            latest = (observed_at, value)

    if latest is None:
        return IndicatorValue(name=name, observed_at=None, value=None)

    return IndicatorValue(
        name=name,
        observed_at=latest[0].isoformat(),
        value=round(latest[1], 4),
    )


def build_market_summary_payload(
    *,
    symbol: str,
    curr_date: str,
    stock_data_text: str,
    indicator_texts: dict[str, str],
) -> dict[str, Any]:
    """Build a normalized market payload from raw vendor outputs."""
    as_of = _parse_date(curr_date)
    frame = parse_stock_data_csv(stock_data_text)
    frame = frame[frame["Date"] <= as_of].copy()
    if frame.empty:
        raise ValueError(f"No stock rows at or before {curr_date}")

    latest = frame.iloc[-1]
    first = frame.iloc[0]
    low = frame.loc[frame["Low"].idxmin()]
    high = frame.loc[frame["High"].idxmax()]
    recent = frame.tail(min(30, len(frame)))
    support = recent.loc[recent["Low"].idxmin()]
    resistance = recent.loc[recent["High"].idxmax()]

    first_close = float(first["Close"])
    latest_close = float(latest["Close"])
    close_return_pct = _pct_change(first_close, latest_close)

    latest_volume = _optional_int(latest["Volume"])
    average_volume = _optional_float(recent["Volume"].mean())
    volume_ratio = (
        round(latest_volume / average_volume, 4)
        if latest_volume is not None and average_volume and average_volume > 0
        else None
    )

    closes = frame["Close"].astype(float)
    daily_returns = closes.pct_change().dropna()
    volatility_pct = (
        round(float(daily_returns.std(ddof=0)) * math.sqrt(252) * 100, 4)
        if len(daily_returns) >= 2
        else None
    )
    max_drawdown_pct = _max_drawdown_pct(closes)

    indicators = {
        name: latest_indicator_value(name, text, curr_date).to_dict()
        for name, text in indicator_texts.items()
    }
    indicator_context = _indicator_context(latest_close, indicators)

    return {
        "schema_version": 1,
        "symbol": symbol.upper(),
        "as_of": curr_date,
        "source": "vendor OHLCV plus stockstats/indicator output",
        "window": {
            "start": first["Date"].isoformat(),
            "end": latest["Date"].isoformat(),
            "row_count": int(len(frame)),
        },
        "price": {
            "latest_date": latest["Date"].isoformat(),
            "latest_close": round(latest_close, 4),
            "latest_open": round(float(latest["Open"]), 4),
            "latest_high": round(float(latest["High"]), 4),
            "latest_low": round(float(latest["Low"]), 4),
            "first_close": round(first_close, 4),
            "close_return_pct": close_return_pct,
            "window_low": round(float(low["Low"]), 4),
            "window_low_date": low["Date"].isoformat(),
            "window_high": round(float(high["High"]), 4),
            "window_high_date": high["Date"].isoformat(),
            "recent_support_low": round(float(support["Low"]), 4),
            "recent_support_date": support["Date"].isoformat(),
            "recent_resistance_high": round(float(resistance["High"]), 4),
            "recent_resistance_date": resistance["Date"].isoformat(),
        },
        "volume": {
            "latest_volume": latest_volume,
            "average_volume_30_rows": _optional_int(average_volume),
            "latest_vs_average_ratio": volume_ratio,
        },
        "risk": {
            "annualized_volatility_pct": volatility_pct,
            "max_drawdown_pct": max_drawdown_pct,
        },
        "indicators": indicators,
        "indicator_context": indicator_context,
    }


def render_market_summary(payload: dict[str, Any]) -> str:
    """Render normalized market facts into a compact markdown tool result."""
    price = payload["price"]
    volume = payload["volume"]
    risk = payload["risk"]
    window = payload["window"]
    context = payload["indicator_context"]

    lines = [
        f"# Deterministic Market Summary: {payload['symbol']}",
        "",
        (
            f"Source window: {window['start']} to {window['end']} "
            f"({window['row_count']} rows), as of {payload['as_of']}."
        ),
        "",
        "## Price, Volume, and Risk",
        "",
        "| Metric | Value | Evidence date/window |",
        "| --- | ---: | --- |",
        (
            f"| Latest OHLC | O {_fmt_money(price['latest_open'])} / "
            f"H {_fmt_money(price['latest_high'])} / "
            f"L {_fmt_money(price['latest_low'])} / "
            f"C {_fmt_money(price['latest_close'])} | {price['latest_date']} |"
        ),
        (
            f"| Window close return | {_fmt_pct(price['close_return_pct'])} | "
            f"{window['start']} close {_fmt_money(price['first_close'])} to "
            f"{price['latest_date']} close {_fmt_money(price['latest_close'])} |"
        ),
        (
            f"| Window low | {_fmt_money(price['window_low'])} | "
            f"{price['window_low_date']} |"
        ),
        (
            f"| Window high | {_fmt_money(price['window_high'])} | "
            f"{price['window_high_date']} |"
        ),
        (
            f"| Recent support low | {_fmt_money(price['recent_support_low'])} | "
            f"last 30 rows, {price['recent_support_date']} |"
        ),
        (
            f"| Recent resistance high | {_fmt_money(price['recent_resistance_high'])} | "
            f"last 30 rows, {price['recent_resistance_date']} |"
        ),
        (
            f"| Latest volume vs 30-row average | {_fmt_volume_ratio(volume)} | "
            f"{price['latest_date']} |"
        ),
        (
            f"| Annualized volatility | {_fmt_pct(risk['annualized_volatility_pct'])} | "
            f"{window['start']} to {window['end']} |"
        ),
        (
            f"| Max drawdown | {_fmt_pct(risk['max_drawdown_pct'])} | "
            f"{window['start']} to {window['end']} |"
        ),
        "",
        "## Technical Indicators",
        "",
        "| Indicator | Latest value | Evidence date | Deterministic interpretation |",
        "| --- | ---: | --- | --- |",
    ]

    for name in DEFAULT_MARKET_INDICATORS:
        item = payload["indicators"].get(name) or {}
        lines.append(
            f"| {name} | {_fmt_plain(item.get('value'))} | "
            f"{item.get('observed_at') or 'N/A'} | "
            f"{context.get(name) or 'No parseable value'} |"
        )

    lines.extend(
        [
            "",
            "## Analyst Guardrails",
            "",
            "- Use these deterministic market values exactly when citing price action, volume, volatility, RSI, MACD, or moving averages.",
            "- Do not infer prices, indicator readings, or ranges that are absent from this summary.",
            "- This summary is analysis input only and is not a BUY/HOLD/SELL portfolio decision.",
        ]
    )
    return "\n".join(lines)


def build_market_summary(
    *,
    symbol: str,
    curr_date: str,
    stock_data_text: str,
    indicator_texts: dict[str, str],
) -> str:
    payload = build_market_summary_payload(
        symbol=symbol,
        curr_date=curr_date,
        stock_data_text=stock_data_text,
        indicator_texts=indicator_texts,
    )
    return render_market_summary(payload)


def _normalise_stock_columns(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "date": "Date",
        "time": "Date",
        "timestamp": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adjusted_close": "Adj Close",
        "adjusted close": "Adj Close",
        "volume": "Volume",
    }
    renamed: dict[str, str] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower().replace(" ", "_")
        renamed[column] = aliases.get(normalized, str(column).strip())
    frame = frame.rename(columns=renamed)

    if "Date" not in frame.columns and len(frame.columns) > 0:
        first_column = frame.columns[0]
        parsed = pd.to_datetime(frame[first_column], errors="coerce")
        if parsed.notna().any():
            frame = frame.rename(columns={first_column: "Date"})

    return frame


def _indicator_context(
    latest_close: float,
    indicators: dict[str, dict[str, Any]],
) -> dict[str, str]:
    context: dict[str, str] = {}
    for name, item in indicators.items():
        value = item.get("value")
        if value is None:
            context[name] = "No parseable value"
            continue

        numeric = float(value)
        if name in {"close_50_sma", "close_200_sma"}:
            label = "50-day SMA" if name == "close_50_sma" else "200-day SMA"
            diff_pct = _pct_change(numeric, latest_close)
            direction = "above" if diff_pct is not None and diff_pct >= 0 else "below"
            context[name] = (
                f"Latest close is {abs(diff_pct or 0):.2f}% {direction} the {label}."
            )
        elif name == "rsi":
            if numeric >= 70:
                context[name] = "Overbought by the standard 70 RSI threshold."
            elif numeric <= 30:
                context[name] = "Oversold by the standard 30 RSI threshold."
            else:
                context[name] = "Neutral; between 30 and 70, so not overbought or oversold."
        elif name == "macd":
            if numeric > 0:
                context[name] = "Positive MACD reading."
            elif numeric < 0:
                context[name] = "Negative MACD reading."
            else:
                context[name] = "Flat MACD reading."
        else:
            context[name] = "Parsed indicator value."
    return context


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _pct_change(start: float, end: float) -> float | None:
    if start == 0:
        return None
    return round(((end / start) - 1.0) * 100, 4)


def _max_drawdown_pct(closes: pd.Series) -> float | None:
    if closes.empty:
        return None
    running_high = closes.cummax()
    drawdowns = (closes / running_high - 1.0) * 100
    return round(float(drawdowns.min()), 4)


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(round(float(value)))


def _fmt_money(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"${float(value):,.2f}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):+.2f}%"


def _fmt_plain(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.2f}"


def _fmt_volume_ratio(volume: dict[str, Any]) -> str:
    latest = volume.get("latest_volume")
    average = volume.get("average_volume_30_rows")
    ratio = volume.get("latest_vs_average_ratio")
    if latest is None or average is None or ratio is None:
        return "N/A"
    return f"{latest:,} vs {average:,} ({ratio:.2f}x)"
