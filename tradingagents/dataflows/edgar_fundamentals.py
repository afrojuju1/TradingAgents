from __future__ import annotations

import os
import threading
from datetime import date, datetime
from typing import Any, Iterable
from urllib.parse import quote

import httpx
import pandas as pd

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.exceptions import DataVendorUnavailableError

_CONFIG_LOCK = threading.Lock()
_CONFIGURED_EDGAR: tuple[str, str | None, float] | None = None
_FACTS_CACHE: dict[tuple[str, tuple[str, str | None, float]], Any] = {}


BALANCE_SHEET_CONCEPTS = {
    "cash_and_equivalents": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
    ),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "short_term_debt": (
        "ShortTermBorrowings",
        "ShortTermDebt",
        "ShortTermBorrowingsAndCurrentMaturitiesOfLongTermDebt",
    ),
    "current_debt": (
        "LongTermDebtCurrent",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "CurrentPortionOfLongTermDebt",
    ),
    "long_term_debt": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebt",
    ),
}

BALANCE_SHEET_SNAPSHOT_CONCEPTS = {
    metric: concepts
    for metric, concepts in BALANCE_SHEET_CONCEPTS.items()
    if metric not in {"short_term_debt", "current_debt", "long_term_debt"}
}

INCOME_STATEMENT_CONCEPTS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "net_income": (
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
        "NetIncomeLoss",
    ),
    "diluted_eps": ("EarningsPerShareDiluted",),
}

CASH_FLOW_CONCEPTS = {
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditures": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalExpenditures",
    ),
    "dividends_paid": (
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfOrdinaryDividends",
    ),
    "share_repurchases": (
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ),
}

METRIC_LABELS = {
    "cash_and_equivalents": "Cash and equivalents",
    "current_assets": "Current assets",
    "current_liabilities": "Current liabilities",
    "total_assets": "Total assets",
    "total_liabilities": "Total liabilities",
    "stockholders_equity": "Stockholders' equity",
    "short_term_debt": "Short-term debt",
    "current_debt": "Current debt",
    "long_term_debt": "Long-term debt",
    "total_debt": "Total debt",
    "net_debt": "Net debt",
    "debt_to_equity": "Debt to equity",
    "current_ratio": "Current ratio",
    "revenue": "Revenue",
    "gross_profit": "Gross profit",
    "operating_income": "Operating income",
    "pretax_income": "Pretax income",
    "net_income": "Net income",
    "diluted_eps": "Diluted EPS",
    "operating_cash_flow": "Operating cash flow",
    "capital_expenditures": "Capital expenditures",
    "dividends_paid": "Dividends paid",
    "share_repurchases": "Share repurchases",
    "free_cash_flow": "Free cash flow",
}


def _parse_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except (TypeError, ValueError):
        return None


def _as_of_date(curr_date: str | None) -> date:
    if curr_date:
        parsed = _parse_date(curr_date)
        if parsed:
            return parsed
    return date.today()


def _concept_variants(concepts: Iterable[str]) -> list[str]:
    variants: list[str] = []
    for concept in concepts:
        candidates = [concept]
        if ":" in concept:
            candidates.append(concept.split(":", 1)[1])
        else:
            candidates.append(f"us-gaap:{concept}")
        for candidate in candidates:
            if candidate not in variants:
                variants.append(candidate)
    return variants


def _read_env_file(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        return {}
    return values


def _gluetun_proxy_from_env_file(path: str | None) -> str | None:
    if not path:
        return None

    values = _read_env_file(path)
    host = values.get("GLUETUN_BIND_IP") or "100.111.132.114"
    user = values.get("HTTPPROXY_USER")
    password = values.get("HTTPPROXY_PASSWORD")
    if not user or not password:
        return None

    return f"http://{quote(user, safe='')}:{quote(password, safe='')}@{host}:8888"


def _resolve_proxy_url(config: dict[str, Any]) -> str | None:
    proxy_url = config.get("sec_proxy_url") or os.environ.get("TRADINGAGENTS_SEC_PROXY_URL")
    if proxy_url:
        return proxy_url

    if config.get("sec_use_gluetun") or os.environ.get("TRADINGAGENTS_SEC_USE_GLUETUN"):
        env_path = (
            config.get("gluetun_env_path")
            or os.environ.get("TRADINGAGENTS_GLUETUN_ENV_PATH")
        )
        return _gluetun_proxy_from_env_file(env_path)

    return None


def _configure_edgar() -> tuple[str, str | None, float]:
    global _CONFIGURED_EDGAR

    config = get_config()
    identity = config.get("sec_identity") or os.environ.get("EDGAR_IDENTITY")
    if not identity:
        raise DataVendorUnavailableError(
            "SEC identity is not configured. Set TRADINGAGENTS_SEC_IDENTITY or EDGAR_IDENTITY."
        )

    try:
        from edgar import set_identity
        from edgar.httpclient import HTTP_MGR, configure_http
    except ImportError as exc:
        raise DataVendorUnavailableError("edgartools is not installed") from exc

    proxy_url = _resolve_proxy_url(config)
    timeout = float(config.get("sec_request_timeout") or 30)
    config_key = (identity, proxy_url, timeout)

    with _CONFIG_LOCK:
        if _CONFIGURED_EDGAR == config_key:
            return config_key

        set_identity(identity)
        if proxy_url:
            configure_http(proxy=proxy_url, timeout=timeout)
        else:
            configure_http(timeout=timeout)
            if HTTP_MGR.httpx_params.pop("proxy", None) is not None:
                HTTP_MGR.close()
        _CONFIGURED_EDGAR = config_key
    return config_key


def _map_edgar_exception(exc: Exception) -> DataVendorUnavailableError | None:
    if isinstance(exc, DataVendorUnavailableError):
        return exc

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        if status in {403, 407, 408, 409, 425, 429, 500, 502, 503, 504}:
            return DataVendorUnavailableError(f"SEC request failed with HTTP {status}")

    if isinstance(
        exc,
        (
            httpx.ProxyError,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.TimeoutException,
            httpx.RequestError,
        ),
    ):
        return DataVendorUnavailableError(f"SEC request failed: {type(exc).__name__}")

    # edgartools defines a few custom exceptions but their import paths have
    # moved across versions. Match by class name to keep this adapter stable.
    if type(exc).__name__ in {
        "IdentityNotSetException",
        "TooManyRequestsError",
    }:
        return DataVendorUnavailableError(f"SEC request failed: {type(exc).__name__}")

    return None


def _load_company_facts(ticker: str):
    try:
        config_key = _configure_edgar()
        from edgar import Company

        cache_key = (ticker.upper(), config_key)
        with _CONFIG_LOCK:
            cached = _FACTS_CACHE.get(cache_key)
            if cached is not None:
                return cached
            facts = Company(ticker.upper()).get_facts()
            _FACTS_CACHE[cache_key] = facts
            return facts
    except Exception as exc:
        unavailable = _map_edgar_exception(exc)
        if unavailable:
            raise unavailable from exc
        raise


def _empty_facts_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "concept",
            "label",
            "numeric_value",
            "unit",
            "period_type",
            "period_start",
            "period_end",
            "fiscal_year",
            "fiscal_period",
            "filing_date",
            "form_type",
            "accession",
            "statement_type",
            "data_quality",
            "confidence_score",
        ]
    )


def _exact_concept_rows(facts: Any, concepts: Iterable[str], as_of: date) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    variants = _concept_variants(concepts)

    query_factory = getattr(facts, "query", None)
    if callable(query_factory):
        for concept in variants:
            query = query_factory().by_concept(concept, exact=True)
            if hasattr(query, "as_of"):
                query = query.as_of(as_of)
            frame = query.to_dataframe()
            if not frame.empty:
                frames.append(frame)

    if not frames and hasattr(facts, "to_dataframe"):
        frame = facts.to_dataframe(include_metadata=True, pit_mode=True)
        if not frame.empty and "concept" in frame.columns:
            frames.append(frame[frame["concept"].isin(variants)])

    if not frames:
        return _empty_facts_df()

    rows = pd.concat(frames, ignore_index=True)
    for column in _empty_facts_df().columns:
        if column not in rows.columns:
            rows[column] = None

    rows["period_end_date"] = rows["period_end"].map(_parse_date)
    rows["period_start_date"] = rows["period_start"].map(_parse_date)
    rows["filing_date_date"] = rows["filing_date"].map(_parse_date)
    rows = rows[rows["numeric_value"].notna()]
    rows = rows[
        rows["filing_date_date"].isna()
        | (rows["filing_date_date"] <= as_of)
    ]
    rows = rows[
        rows["period_end_date"].isna()
        | (rows["period_end_date"] <= as_of)
    ]
    return rows


def _filter_period_type(rows: pd.DataFrame, period_type: str) -> pd.DataFrame:
    if rows.empty or "period_type" not in rows.columns:
        return rows
    return rows[rows["period_type"].fillna("").astype(str).str.lower() == period_type]


def _filter_frequency(rows: pd.DataFrame, freq: str) -> pd.DataFrame:
    if rows.empty:
        return rows

    annual = freq.lower() == "annual"
    rows = rows.copy()
    rows["duration_days"] = rows.apply(
        lambda row: (
            (row["period_end_date"] - row["period_start_date"]).days + 1
            if row["period_start_date"] and row["period_end_date"]
            else None
        ),
        axis=1,
    )

    fiscal_period = rows["fiscal_period"].fillna("").astype(str).str.upper()
    duration_days = rows["duration_days"]
    if annual:
        return rows[(fiscal_period == "FY") | (duration_days >= 300)]
    return rows[(fiscal_period != "FY") & ((duration_days.isna()) | (duration_days <= 140))]


def _sort_fact_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    rows = rows.copy()
    rows["confidence_sort"] = pd.to_numeric(rows["confidence_score"], errors="coerce").fillna(0.0)
    rows["abs_value_sort"] = pd.to_numeric(rows["numeric_value"], errors="coerce").abs().fillna(0.0)
    return rows.sort_values(
        by=[
            "period_end_date",
            "filing_date_date",
            "confidence_sort",
            "abs_value_sort",
        ],
        na_position="first",
    )


def _latest_row(
    facts: Any,
    concepts: Iterable[str],
    as_of: date,
    *,
    period_type: str,
    freq: str | None = None,
    period_end: date | None = None,
) -> dict[str, Any] | None:
    rows = _exact_concept_rows(facts, concepts, as_of)
    rows = _filter_period_type(rows, period_type)
    if freq:
        rows = _filter_frequency(rows, freq)
    if period_end:
        rows = rows[rows["period_end_date"] == period_end]
    if rows.empty:
        return None
    return _sort_fact_rows(rows).iloc[-1].to_dict()


def _latest_metric_rows(
    facts: Any,
    registry: dict[str, tuple[str, ...]],
    as_of: date,
    *,
    period_type: str,
    freq: str | None = None,
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for metric, concepts in registry.items():
        row = _latest_row(
            facts,
            concepts,
            as_of,
            period_type=period_type,
            freq=freq,
        )
        if row:
            selected[metric] = row
    return selected


def _latest_period_end(
    facts: Any,
    registry: dict[str, tuple[str, ...]],
    as_of: date,
    *,
    period_type: str,
    freq: str | None = None,
) -> date | None:
    periods: list[date] = []
    for concepts in registry.values():
        rows = _exact_concept_rows(facts, concepts, as_of)
        rows = _filter_period_type(rows, period_type)
        if freq:
            rows = _filter_frequency(rows, freq)
        periods.extend(period for period in rows["period_end_date"].tolist() if period)
    return max(periods) if periods else None


def _metric_rows_for_period(
    facts: Any,
    registry: dict[str, tuple[str, ...]],
    as_of: date,
    *,
    period_type: str,
    period_end: date,
    freq: str | None = None,
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for metric, concepts in registry.items():
        row = _latest_row(
            facts,
            concepts,
            as_of,
            period_type=period_type,
            freq=freq,
            period_end=period_end,
        )
        if row:
            selected[metric] = row
    return selected


def _period_consistent_metric_rows(
    facts: Any,
    registry: dict[str, tuple[str, ...]],
    as_of: date,
    *,
    period_type: str,
    freq: str | None = None,
) -> tuple[dict[str, dict[str, Any]], date | None]:
    period_end = _latest_period_end(
        facts,
        registry,
        as_of,
        period_type=period_type,
        freq=freq,
    )
    if not period_end:
        return {}, None
    return (
        _metric_rows_for_period(
            facts,
            registry,
            as_of,
            period_type=period_type,
            freq=freq,
            period_end=period_end,
        ),
        period_end,
    )


def _latest_common_instant_period(
    facts: Any,
    metrics: Iterable[str],
    as_of: date,
) -> date | None:
    common_periods: set[date] | None = None
    for metric in metrics:
        rows = _exact_concept_rows(facts, BALANCE_SHEET_CONCEPTS[metric], as_of)
        rows = _filter_period_type(rows, "instant")
        periods = {period for period in rows["period_end_date"].tolist() if period}
        common_periods = periods if common_periods is None else common_periods & periods
    return max(common_periods) if common_periods else None


def _period_label(row: dict[str, Any]) -> str:
    period_start = _parse_date(row.get("period_start"))
    period_end = _parse_date(row.get("period_end"))
    if row.get("period_type") == "instant":
        return f"as of {period_end.isoformat()}" if period_end else "instant date unknown"
    if period_start and period_end:
        days = (period_end - period_start).days + 1
        if days >= 300:
            return f"FY ended {period_end.isoformat()}"
        return f"{days}D ended {period_end.isoformat()}"
    return str(period_end or "period unknown")


def _format_value(value: float | int | None, unit: str | None = "USD") -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    unit_upper = (unit or "").upper()
    prefix = "$" if unit_upper in {"USD", "US DOLLARS"} else ""
    abs_value = abs(number)
    if abs_value >= 1_000_000_000:
        return f"{prefix}{number / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{prefix}{number / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{prefix}{number / 1_000:.2f}K"
    return f"{prefix}{number:.2f}"


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _metadata(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("period_end") or ""),
        str(row.get("filing_date") or ""),
        str(row.get("form_type") or ""),
        str(row.get("accession") or ""),
    )


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "No SEC facts found."
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _fact_table(selected: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for metric, row in selected.items():
        period_end, filing_date, form_type, accession = _metadata(row)
        rows.append(
            [
                METRIC_LABELS.get(metric, metric),
                _format_value(row.get("numeric_value"), row.get("unit")),
                _period_label(row),
                filing_date,
                form_type,
                accession,
                row.get("concept") or "",
            ]
        )
    return _markdown_table(
        ["Metric", "Value", "Period", "Filing Date", "Form", "Accession", "Concept"],
        rows,
    )


def _same_period_component(
    facts: Any,
    metric: str,
    as_of: date,
    period_end: date,
) -> dict[str, Any] | None:
    return _latest_row(
        facts,
        BALANCE_SHEET_CONCEPTS[metric],
        as_of,
        period_type="instant",
        period_end=period_end,
    )


def _latest_debt_period(facts: Any, as_of: date) -> date | None:
    periods: list[date] = []
    for metric in ("short_term_debt", "current_debt", "long_term_debt"):
        rows = _exact_concept_rows(facts, BALANCE_SHEET_CONCEPTS[metric], as_of)
        rows = _filter_period_type(rows, "instant")
        periods.extend(period for period in rows["period_end_date"].tolist() if period)
    return max(periods) if periods else None


def _derive_balance_metrics(facts: Any, as_of: date) -> dict[str, dict[str, Any]]:
    derived: dict[str, dict[str, Any]] = {}

    debt_period_end = _latest_debt_period(facts, as_of)
    if debt_period_end:
        components = {
            metric: _same_period_component(facts, metric, as_of, debt_period_end)
            for metric in ("short_term_debt", "current_debt", "long_term_debt")
        }
        present_components = {metric: row for metric, row in components.items() if row}
        if present_components:
            total_debt = sum(float(row["numeric_value"]) for row in present_components.values())
            source = max(
                present_components.values(),
                key=lambda row: _parse_date(row.get("filing_date")) or date.min,
            )
            derived["total_debt"] = {
                **source,
                "numeric_value": total_debt,
                "concept": "+".join(row.get("concept", "") for row in present_components.values()),
                "component_metrics": list(present_components),
            }

            cash = _same_period_component(facts, "cash_and_equivalents", as_of, debt_period_end)
            if cash:
                derived["net_debt"] = {
                    **source,
                    "numeric_value": total_debt - float(cash["numeric_value"]),
                    "concept": f"total_debt-{cash.get('concept', '')}",
                    "component_metrics": [*present_components, "cash_and_equivalents"],
                }

            equity = _same_period_component(facts, "stockholders_equity", as_of, debt_period_end)
            if equity and float(equity["numeric_value"]) != 0:
                derived["debt_to_equity"] = {
                    **source,
                    "numeric_value": total_debt / float(equity["numeric_value"]),
                    "unit": "ratio",
                    "concept": f"total_debt/{equity.get('concept', '')}",
                    "component_metrics": [*present_components, "stockholders_equity"],
                }

    liquidity_period_end = _latest_common_instant_period(
        facts,
        ("current_assets", "current_liabilities"),
        as_of,
    )
    if not liquidity_period_end:
        return derived

    current_assets = _same_period_component(facts, "current_assets", as_of, liquidity_period_end)
    current_liabilities = _same_period_component(facts, "current_liabilities", as_of, liquidity_period_end)
    if (
        current_assets
        and current_liabilities
        and float(current_liabilities["numeric_value"]) != 0
    ):
        derived["current_ratio"] = {
            **current_assets,
            "numeric_value": float(current_assets["numeric_value"]) / float(current_liabilities["numeric_value"]),
            "unit": "ratio",
            "concept": f"{current_assets.get('concept', '')}/{current_liabilities.get('concept', '')}",
            "component_metrics": ["current_assets", "current_liabilities"],
        }

    return derived


def _derived_table(derived: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for metric, row in derived.items():
        value = (
            _format_ratio(row.get("numeric_value"))
            if row.get("unit") == "ratio"
            else _format_value(row.get("numeric_value"), row.get("unit"))
        )
        components = ", ".join(
            METRIC_LABELS.get(component, component)
            for component in row.get("component_metrics", [])
        )
        period_end, filing_date, form_type, accession = _metadata(row)
        rows.append(
            [
                METRIC_LABELS.get(metric, metric),
                value,
                components,
                period_end,
                filing_date,
                form_type,
                accession,
                row.get("concept") or "",
            ]
        )
    return _markdown_table(
        ["Metric", "Value", "Components", "Period End", "Filing Date", "Form", "Accession", "Source Concepts"],
        rows,
    )


def _derive_cash_flow_metrics(selected: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    operating_cash_flow = selected.get("operating_cash_flow")
    capex = selected.get("capital_expenditures")
    if not operating_cash_flow or not capex:
        return {}
    if _parse_date(operating_cash_flow.get("period_end")) != _parse_date(capex.get("period_end")):
        return {}

    return {
        "free_cash_flow": {
            **operating_cash_flow,
            "numeric_value": float(operating_cash_flow["numeric_value"]) - abs(float(capex["numeric_value"])),
            "concept": f"{operating_cash_flow.get('concept', '')}-{capex.get('concept', '')}",
            "component_metrics": ["operating_cash_flow", "capital_expenditures"],
        }
    }


def _period_consistency_notes(
    *,
    latest_balance_period: date | None,
    derived: dict[str, dict[str, Any]],
) -> str:
    if not latest_balance_period:
        return ""

    stale_metrics: list[str] = []
    for metric, row in derived.items():
        metric_period = _parse_date(row.get("period_end"))
        if metric_period and metric_period < latest_balance_period:
            stale_metrics.append(f"{METRIC_LABELS.get(metric, metric)} ({metric_period.isoformat()})")

    if not stale_metrics:
        return ""

    return (
        "## Data Quality Notes\n\n"
        f"- Latest balance sheet snapshot period is {latest_balance_period.isoformat()}.\n"
        f"- These derived metrics use older same-period components: {', '.join(stale_metrics)}.\n"
        "- Do not describe older derived debt metrics as current-quarter values.\n\n"
    )


def _section_header(title: str, ticker: str, curr_date: str | None) -> str:
    as_of = _as_of_date(curr_date)
    return (
        f"# {title} for {ticker.upper()}\n"
        f"# Source: SEC EDGAR via edgartools\n"
        f"# Facts available as of trading date: {as_of.isoformat()}\n\n"
    )


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    facts = _load_company_facts(ticker)
    as_of = _as_of_date(curr_date)
    selected, latest_balance_period = _period_consistent_metric_rows(
        facts,
        BALANCE_SHEET_CONCEPTS,
        as_of,
        period_type="instant",
    )
    if not selected:
        raise DataVendorUnavailableError(f"No SEC balance sheet facts found for {ticker}")

    derived = _derive_balance_metrics(facts, as_of)
    return (
        _section_header("SEC Balance Sheet", ticker, curr_date)
        + "Reported facts are anchored to one latest balance sheet period. "
        + "Debt-derived metrics may use an older period only when same-period debt components are not reported in the latest filing.\n\n"
        + _period_consistency_notes(
            latest_balance_period=latest_balance_period,
            derived=derived,
        )
        + "## Derived Debt And Liquidity\n\n"
        + _derived_table(derived)
        + "\n\n## Reported Facts - Period-Consistent Snapshot\n\n"
        + _fact_table(selected)
    )


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    facts = _load_company_facts(ticker)
    as_of = _as_of_date(curr_date)
    selected, period_end = _period_consistent_metric_rows(
        facts,
        INCOME_STATEMENT_CONCEPTS,
        as_of,
        period_type="duration",
        freq=freq,
    )
    if not selected:
        raise DataVendorUnavailableError(f"No SEC income statement facts found for {ticker}")
    period_note = (
        f"Reported facts are anchored to period end {period_end.isoformat()}.\n\n"
        if period_end
        else ""
    )
    return _section_header("SEC Income Statement", ticker, curr_date) + period_note + _fact_table(selected)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    facts = _load_company_facts(ticker)
    as_of = _as_of_date(curr_date)
    selected, period_end = _period_consistent_metric_rows(
        facts,
        CASH_FLOW_CONCEPTS,
        as_of,
        period_type="duration",
        freq=freq,
    )
    if not selected:
        raise DataVendorUnavailableError(f"No SEC cash flow facts found for {ticker}")

    derived = _derive_cash_flow_metrics(selected)
    return (
        _section_header("SEC Cash Flow", ticker, curr_date)
        + (
            f"Reported facts are anchored to period end {period_end.isoformat()}.\n\n"
            if period_end
            else ""
        )
        + "## Derived Cash Flow\n\n"
        + _derived_table(derived)
        + "\n\n## Reported Facts - Period-Consistent Snapshot\n\n"
        + _fact_table(selected)
    )


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    facts = _load_company_facts(ticker)
    as_of = _as_of_date(curr_date)

    balance, latest_balance_period = _period_consistent_metric_rows(
        facts,
        BALANCE_SHEET_CONCEPTS,
        as_of,
        period_type="instant",
    )
    income, latest_income_period = _period_consistent_metric_rows(
        facts,
        INCOME_STATEMENT_CONCEPTS,
        as_of,
        period_type="duration",
        freq="quarterly",
    )
    cash_flow, latest_cash_flow_period = _period_consistent_metric_rows(
        facts,
        CASH_FLOW_CONCEPTS,
        as_of,
        period_type="duration",
        freq="quarterly",
    )
    if not any([balance, income, cash_flow]):
        raise DataVendorUnavailableError(f"No SEC facts found for {ticker}")

    debt_and_liquidity = _derive_balance_metrics(facts, as_of)
    derived_cash_flow = _derive_cash_flow_metrics(cash_flow)

    return (
        _section_header("SEC Fundamentals", ticker, curr_date)
        + "SEC statement facts are selected point-in-time by filing date and exact XBRL concept. "
        + "Market valuation fields should still come from market-data tools. "
        + "Each reported statement snapshot is period-consistent; missing metrics are omitted instead of backfilled from older periods.\n\n"
        + _period_consistency_notes(
            latest_balance_period=latest_balance_period,
            derived=debt_and_liquidity,
        )
        + "## Derived Debt And Liquidity\n\n"
        + _derived_table(debt_and_liquidity)
        + "\n\n## Balance Sheet Snapshot - Period-Consistent"
        + (f" ({latest_balance_period.isoformat()})" if latest_balance_period else "")
        + "\n\n"
        + _fact_table(balance)
        + "\n\n## Income Statement Snapshot - Period-Consistent"
        + (f" ({latest_income_period.isoformat()})" if latest_income_period else "")
        + "\n\n"
        + _fact_table(income)
        + "\n\n## Cash Flow Snapshot - Period-Consistent"
        + (f" ({latest_cash_flow_period.isoformat()})" if latest_cash_flow_period else "")
        + "\n\n"
        + _fact_table(cash_flow)
        + "\n\n## Derived Cash Flow\n\n"
        + _derived_table(derived_cash_flow)
    )
