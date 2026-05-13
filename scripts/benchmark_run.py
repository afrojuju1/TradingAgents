from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from cli.main import save_report_to_disk
from cli.stats_handler import StatsCallbackHandler
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.report_quality import check_report_quality
from tradingagents.run_profiles import apply_run_profile


_NODE_END_RE = re.compile(r"Node end: (?P<name>.+) elapsed=(?P<elapsed>[0-9.]+)s")
_ANALYST_DONE_RE = re.compile(
    r"Analyst completed: (?P<name>.+) elapsed=(?P<elapsed>[0-9.]+)s"
)


class TimingLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.node_timings: list[dict[str, Any]] = []
        self.analyst_timings: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        node_match = _NODE_END_RE.search(message)
        if node_match:
            self.node_timings.append(
                {
                    "node": node_match.group("name"),
                    "elapsed_seconds": float(node_match.group("elapsed")),
                }
            )
            return

        analyst_match = _ANALYST_DONE_RE.search(message)
        if analyst_match:
            self.analyst_timings.append(
                {
                    "analyst": analyst_match.group("name"),
                    "elapsed_seconds": float(analyst_match.group("elapsed")),
                }
            )


def _command_snapshot(command: list[str], timeout: int = 10) -> dict[str, Any]:
    executable = shutil.which(command[0])
    if executable is None:
        return {"available": False, "command": command}

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {
            "available": True,
            "command": command,
            "status": "error",
            "error_type": type(exc).__name__,
        }

    return {
        "available": True,
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _quality_summary(issues: list[dict[str, Any]]) -> dict[str, Any]:
    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    return {
        "passed": error_count == 0,
        "errors": error_count,
        "warnings": warning_count,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a non-interactive TradingAgents benchmark and write run metadata."
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol to analyze.")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Trade date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--profile",
        choices=["fast", "balanced", "quality"],
        default=None,
        help="Optional local run profile override.",
    )
    parser.add_argument(
        "--output-root",
        default="reports",
        help="Directory where benchmark report folders are written.",
    )
    parser.add_argument(
        "--llm-provider",
        default=None,
        help="Optional LLM provider override, e.g. ollama.",
    )
    parser.add_argument("--quick-model", default=None, help="Quick model override.")
    parser.add_argument("--deep-model", default=None, help="Deep model override.")
    parser.add_argument(
        "--backend-url",
        default=None,
        help="Optional LLM backend URL override.",
    )
    parser.add_argument(
        "--prefetch",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable deterministic prefetch for this run.",
    )
    parser.add_argument(
        "--require-sec",
        action="store_true",
        help="Mark quality metadata failed when SEC evidence is missing.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    ticker = args.ticker.upper()
    safe_ticker = safe_ticker_component(ticker)

    config = copy.deepcopy(DEFAULT_CONFIG)
    if args.profile:
        config = apply_run_profile(config, args.profile)

    if args.llm_provider:
        config["llm_provider"] = args.llm_provider
    if args.quick_model:
        config["quick_think_llm"] = args.quick_model
    if args.deep_model:
        config["deep_think_llm"] = args.deep_model
    if args.backend_url:
        config["backend_url"] = args.backend_url
    if args.prefetch is not None:
        config["prefetch_data_enabled"] = bool(args.prefetch)

    output_root = Path(args.output_root).expanduser().resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = output_root / f"{safe_ticker}_{timestamp}"
    config["results_dir"] = str(output_root / "_state_logs")

    stats = StatsCallbackHandler()
    timing_handler = TimingLogHandler()
    setup_logger = logging.getLogger("tradingagents.graph.setup")
    previous_level = setup_logger.level
    setup_logger.setLevel(logging.INFO)
    setup_logger.addHandler(timing_handler)

    start = time.perf_counter()
    try:
        graph = TradingAgentsGraph(
            selected_analysts=config.get("selected_analysts"),
            config=config,
            callbacks=[stats],
        )
        final_state, signal = graph.propagate(ticker, args.date)
    finally:
        setup_logger.removeHandler(timing_handler)
        setup_logger.setLevel(previous_level)

    wall_seconds = time.perf_counter() - start
    report_path = save_report_to_disk(final_state, ticker, report_dir)
    quality_issues = [
        asdict(issue)
        for issue in check_report_quality(report_dir, require_sec=args.require_sec)
    ]

    metadata = {
        "ticker": ticker,
        "trade_date": args.date,
        "run_profile": config.get("run_profile"),
        "signal": signal,
        "wall_seconds": wall_seconds,
        "report_path": str(report_path),
        "config": {
            "llm_provider": config.get("llm_provider"),
            "quick_think_llm": config.get("quick_think_llm"),
            "deep_think_llm": config.get("deep_think_llm"),
            "backend_url": config.get("backend_url"),
            "selected_analysts": config.get("selected_analysts"),
            "parallel_analysts": config.get("parallel_analysts"),
            "parallel_analyst_workers": config.get("parallel_analyst_workers"),
            "prefetch_data_enabled": config.get("prefetch_data_enabled"),
            "data_tool_cache_enabled": config.get("data_tool_cache_enabled"),
            "fundamental_data_vendor": config.get("data_vendors", {}).get(
                "fundamental_data"
            ),
        },
        "llm_stats": stats.get_stats(),
        "node_timings": timing_handler.node_timings,
        "parallel_analyst_timings": timing_handler.analyst_timings,
        "data_tool_events": final_state.get("data_tool_events", []),
        "quality": _quality_summary(quality_issues),
        "quality_issues": quality_issues,
        "environment": {
            "ollama_ps": _command_snapshot(["ollama", "ps"]),
            "nvidia_smi": _command_snapshot(
                [
                    "nvidia-smi",
                    "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ]
            ),
            "gluetun": _command_snapshot(
                [
                    "docker",
                    "ps",
                    "--filter",
                    "name=gluetun",
                    "--format",
                    "{{.Names}}\t{{.Status}}\t{{.Ports}}",
                ]
            ),
        },
    }

    metadata_path = report_dir / "run_metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False, default=str))
    return 1 if not metadata["quality"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
