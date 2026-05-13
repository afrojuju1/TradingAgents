from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Iterable

from tradingagents.dataflows.interface import route_to_vendor

logger = logging.getLogger(__name__)

COMMON_PREFETCH_INDICATORS = (
    "close_50_sma",
    "close_200_sma",
    "rsi",
    "macd",
)


@dataclass(frozen=True)
class PrefetchTask:
    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


def _date_window(trade_date: str, days: int) -> tuple[str, str]:
    end = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _market_stock_window(trade_date: str, days: int) -> tuple[str, str]:
    start, end = _date_window(trade_date, days)
    end_exclusive = datetime.strptime(end, "%Y-%m-%d").date() + timedelta(days=1)
    return start, end_exclusive.isoformat()


def build_prefetch_tasks(
    ticker: str,
    trade_date: str,
    selected_analysts: Iterable[str],
    config: dict[str, Any],
) -> list[PrefetchTask]:
    selected = set(selected_analysts)
    tasks: list[PrefetchTask] = []

    if "market" in selected:
        start_date, end_date = _market_stock_window(trade_date, 365)
        tasks.append(PrefetchTask("get_stock_data", (ticker, start_date, end_date), {}))
        for indicator in COMMON_PREFETCH_INDICATORS:
            tasks.append(PrefetchTask("get_indicators", (ticker, indicator, trade_date, 30), {}))

    if "fundamentals" in selected:
        tasks.extend(
            [
                PrefetchTask("get_fundamentals", (ticker, trade_date), {}),
                PrefetchTask("get_balance_sheet", (ticker, "quarterly", trade_date), {}),
                PrefetchTask("get_cashflow", (ticker, "quarterly", trade_date), {}),
                PrefetchTask("get_income_statement", (ticker, "quarterly", trade_date), {}),
            ]
        )

    if "social" in selected or "news" in selected:
        start_date, end_date = _date_window(trade_date, 7)
        tasks.append(PrefetchTask("get_news", (ticker, start_date, end_date), {}))

    if "news" in selected:
        tasks.extend(
            [
                PrefetchTask(
                    "get_global_news",
                    (
                        trade_date,
                        config.get("global_news_lookback_days"),
                        config.get("global_news_article_limit"),
                    ),
                    {},
                ),
                PrefetchTask("get_insider_transactions", (ticker,), {}),
            ]
        )

    return tasks


def _run_task(task: PrefetchTask) -> dict[str, Any]:
    start = perf_counter()
    try:
        result = route_to_vendor(task.method, *task.args, **task.kwargs)
        status = "ok"
        if isinstance(result, str) and result.lstrip().lower().startswith("error "):
            status = "error"
        return {
            "method": task.method,
            "status": status,
            "elapsed_seconds": perf_counter() - start,
        }
    except Exception as exc:
        logger.warning(
            "Prefetch failed for %s%r: %s",
            task.method,
            task.args,
            exc,
        )
        return {
            "method": task.method,
            "status": "error",
            "elapsed_seconds": perf_counter() - start,
            "error": type(exc).__name__,
        }


def prefetch_data(
    ticker: str,
    trade_date: str,
    selected_analysts: Iterable[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not config.get("prefetch_data_enabled", False):
        return []

    if not config.get("data_tool_cache_enabled", False):
        logger.info("Skipping data prefetch because data_tool_cache_enabled is false")
        return []

    tasks = build_prefetch_tasks(ticker, trade_date, selected_analysts, config)
    if not tasks:
        return []

    workers = max(1, int(config.get("prefetch_workers") or 1))
    workers = min(workers, len(tasks))
    logger.info("Prefetching %d data task(s) with %d worker(s)", len(tasks), workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_run_task, task) for task in tasks]
        return [future.result() for future in as_completed(futures)]
