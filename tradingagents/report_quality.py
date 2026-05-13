from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


SEC_SOURCE_MARKER = "# Source: SEC EDGAR via edgartools"
DEFAULT_FORBIDDEN_YEARS = ("2011",)

RECOMMENDATION_HEADING_RE = re.compile(
    r"(?im)^\s{0,3}(?:[-*+]\s+|\d+[\.)]\s+)?(?:#{1,6}\s*)?(?:\*\*)?"
    r"(?:final\s+|investment\s+|portfolio\s+)?recommendation\b"
    r"(?:\s*[:\-])?(?:\*\*)?(?:\s*[:\-].*)?\s*$"
)

ERROR_PATTERNS = (
    ("traceback", re.compile(r"Traceback \(most recent call last\)", re.I)),
    ("vendor_unavailable", re.compile(r"\bDataVendorUnavailableError\b", re.I)),
    ("sec_request_failed", re.compile(r"\bSEC request failed\b", re.I)),
    ("fallback_fundamentals", re.compile(r"\bfallback fundamentals\b", re.I)),
    ("uncaught_exception", re.compile(r"^\s*(?:Exception|Error):", re.I | re.M)),
)

WARNING_PATTERNS = (
    ("missing_sec_facts", re.compile(r"\bNo SEC facts found\b", re.I)),
    ("fallback_text", re.compile(r"\b(?:falling back|using fallback)\b", re.I)),
)


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    path: str
    message: str


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _markdown_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".md" else []
    return sorted(root.rglob("*.md"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _has_sec_metadata(report_root: Path) -> bool:
    for metadata_name in ("run_metadata.json", "run_summary.json"):
        metadata_path = report_root / metadata_name
        if not metadata_path.exists():
            continue
        try:
            payload = json.loads(_read_text(metadata_path))
        except json.JSONDecodeError:
            continue
        serialized = json.dumps(payload).lower()
        if "edgar" in serialized or "sec" in serialized:
            return True
    return False


def _has_sec_source_evidence(report_root: Path, targets: Iterable[Path]) -> bool:
    if _has_sec_metadata(report_root):
        return True
    return any(SEC_SOURCE_MARKER in _read_text(path) for path in targets if path.exists())


def _check_forbidden_years(
    path: Path,
    text: str,
    root: Path,
    forbidden_years: Iterable[str],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for year in forbidden_years:
        if not year:
            continue
        match = re.search(rf"\b{re.escape(year)}\b", text)
        if match:
            issues.append(
                QualityIssue(
                    "error",
                    "stale_year",
                    f"{_display_path(path, root)}:{_line_number(text, match.start())}",
                    f"forbidden stale year {year} appears in report output",
                )
            )
    return issues


def _check_pattern_list(
    path: Path,
    text: str,
    root: Path,
    *,
    severity: str,
    patterns: Sequence[tuple[str, re.Pattern[str]]],
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for code, pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        issues.append(
            QualityIssue(
                severity,
                code,
                f"{_display_path(path, root)}:{_line_number(text, match.start())}",
                f"matched quality pattern {code!r}: {match.group(0).strip()}",
            )
        )
    return issues


def _check_recommendation_leakage(
    fundamentals_path: Path,
    text: str,
    root: Path,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for match in RECOMMENDATION_HEADING_RE.finditer(text):
        issues.append(
            QualityIssue(
                "error",
                "analyst_recommendation_leakage",
                f"{_display_path(fundamentals_path, root)}:{_line_number(text, match.start())}",
                "fundamentals analyst output contains a recommendation heading or label",
            )
        )
    return issues


def check_report_quality(
    report_path: str | Path,
    *,
    require_sec: bool = False,
    forbidden_years: Iterable[str] = DEFAULT_FORBIDDEN_YEARS,
) -> list[QualityIssue]:
    root = Path(report_path).expanduser().resolve()
    report_root = root.parent if root.is_file() else root
    issues: list[QualityIssue] = []

    if not root.exists():
        return [
            QualityIssue(
                "error",
                "report_path_missing",
                str(root),
                "report path does not exist",
            )
        ]

    complete_report = report_root / "complete_report.md"
    if root.is_dir() and not complete_report.exists():
        issues.append(
            QualityIssue(
                "error",
                "complete_report_missing",
                _display_path(complete_report, report_root),
                "report directory is missing complete_report.md",
            )
        )

    markdown_files = _markdown_files(root)
    if not markdown_files:
        issues.append(
            QualityIssue(
                "error",
                "markdown_missing",
                _display_path(root, report_root),
                "no markdown report files found",
            )
        )
        return issues

    for path in markdown_files:
        text = _read_text(path)
        issues.extend(_check_forbidden_years(path, text, report_root, forbidden_years))
        issues.extend(
            _check_pattern_list(
                path,
                text,
                report_root,
                severity="error",
                patterns=ERROR_PATTERNS,
            )
        )
        issues.extend(
            _check_pattern_list(
                path,
                text,
                report_root,
                severity="warning",
                patterns=WARNING_PATTERNS,
            )
        )

    fundamentals_path = report_root / "1_analysts" / "fundamentals.md"
    if fundamentals_path.exists():
        fundamentals_text = _read_text(fundamentals_path)
        issues.extend(
            _check_recommendation_leakage(
                fundamentals_path,
                fundamentals_text,
                report_root,
            )
        )
    elif root.is_dir():
        issues.append(
            QualityIssue(
                "warning",
                "fundamentals_report_missing",
                _display_path(fundamentals_path, report_root),
                "fundamentals analyst report is missing",
            )
        )

    if require_sec:
        sec_targets = [path for path in (fundamentals_path, complete_report) if path.exists()]
        if not _has_sec_source_evidence(report_root, sec_targets):
            issues.append(
                QualityIssue(
                    "error",
                    "sec_source_missing",
                    _display_path(report_root, report_root),
                    "SEC fundamentals were required but no SEC EDGAR source marker was found",
                )
            )

    return issues


def format_issues(issues: Sequence[QualityIssue]) -> str:
    if not issues:
        return "Report quality check passed."
    return "\n".join(
        f"{issue.severity.upper()} {issue.code} {issue.path}: {issue.message}"
        for issue in issues
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check generated TradingAgents reports for common quality regressions.")
    parser.add_argument("report_path", help="Report directory or markdown file to inspect.")
    parser.add_argument("--require-sec", action="store_true", help="Fail if SEC EDGAR source markers are absent.")
    parser.add_argument(
        "--forbid-year",
        action="append",
        default=None,
        help="Year that must not appear in report output. May be provided multiple times.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--strict-warnings", action="store_true", help="Return non-zero when warnings are present.")
    args = parser.parse_args(argv)

    issues = check_report_quality(
        args.report_path,
        require_sec=args.require_sec,
        forbidden_years=args.forbid_year or DEFAULT_FORBIDDEN_YEARS,
    )

    if args.json:
        print(json.dumps([asdict(issue) for issue in issues], indent=2))
    else:
        print(format_issues(issues))

    has_errors = any(issue.severity == "error" for issue in issues)
    has_warnings = any(issue.severity == "warning" for issue in issues)
    return 1 if has_errors or (args.strict_warnings and has_warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
