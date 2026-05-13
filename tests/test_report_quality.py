from __future__ import annotations

from pathlib import Path

from tradingagents.report_quality import check_report_quality, main


def _write_report(root: Path, fundamentals: str, complete: str | None = None) -> None:
    (root / "1_analysts").mkdir(parents=True)
    (root / "1_analysts" / "fundamentals.md").write_text(fundamentals, encoding="utf-8")
    (root / "complete_report.md").write_text(complete or fundamentals, encoding="utf-8")


def _codes(root: Path, **kwargs) -> set[str]:
    return {issue.code for issue in check_report_quality(root, **kwargs)}


def test_report_quality_accepts_sec_report_without_recommendation(tmp_path):
    _write_report(
        tmp_path,
        "# Fundamentals\n# Source: SEC EDGAR via edgartools\n\nNet income uses 2026-03-31 facts.",
    )

    assert check_report_quality(tmp_path, require_sec=True) == []


def test_report_quality_flags_stale_year_and_recommendation_leakage(tmp_path):
    _write_report(
        tmp_path,
        "\n".join(
            [
                "# Fundamentals",
                "# Source: SEC EDGAR via edgartools",
                "Net income from 2011 leaked into the current report.",
                "## Recommendation",
                "3. **Recommendation:**",
                "Buy.",
            ]
        ),
    )

    assert _codes(tmp_path, require_sec=True) == {
        "stale_year",
        "analyst_recommendation_leakage",
    }


def test_report_quality_requires_sec_source_when_requested(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n\nYFinance fundamentals only.")

    assert "sec_source_missing" in _codes(tmp_path, require_sec=True)


def test_report_quality_accepts_sec_metadata_when_model_summary_omits_marker(tmp_path):
    _write_report(tmp_path, "# Fundamentals\n\nModel summary of SEC fundamentals.")
    (tmp_path / "run_metadata.json").write_text(
        '{"fundamental_vendor": "edgar,yfinance"}',
        encoding="utf-8",
    )

    assert "sec_source_missing" not in _codes(tmp_path, require_sec=True)


def test_report_quality_warns_on_missing_sec_facts_without_failing_by_default(tmp_path, capsys):
    _write_report(
        tmp_path,
        "# Fundamentals\n# Source: SEC EDGAR via edgartools\n\nNo SEC facts found.",
    )

    assert main([str(tmp_path), "--require-sec"]) == 0
    output = capsys.readouterr().out
    assert "WARNING missing_sec_facts" in output


def test_report_quality_strict_warnings_returns_nonzero(tmp_path):
    _write_report(
        tmp_path,
        "# Fundamentals\n# Source: SEC EDGAR via edgartools\n\nNo SEC facts found.",
    )

    assert main([str(tmp_path), "--require-sec", "--strict-warnings"]) == 1
