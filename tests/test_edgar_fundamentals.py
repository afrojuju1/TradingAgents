from __future__ import annotations

import copy
from datetime import date

import pandas as pd

import tradingagents.default_config as default_config
from tradingagents.dataflows import edgar_fundamentals, interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.exceptions import DataVendorUnavailableError


class FakeQuery:
    def __init__(self, facts, rows):
        self._facts = facts
        self._rows = list(rows)

    def by_concept(self, concept: str, exact: bool = False):
        self._facts.exact_flags.append(exact)
        if exact:
            rows = [row for row in self._rows if row["concept"] == concept]
        else:
            needle = concept.lower()
            rows = [row for row in self._rows if needle in row["concept"].lower()]
        return FakeQuery(self._facts, rows)

    def as_of(self, as_of_date: date):
        rows = [
            row
            for row in self._rows
            if pd.to_datetime(row["filing_date"]).date() <= as_of_date
        ]
        return FakeQuery(self._facts, rows)

    def to_dataframe(self):
        return pd.DataFrame(self._rows)


class FakeFacts:
    def __init__(self, rows):
        self._rows = rows
        self.exact_flags = []

    def query(self):
        return FakeQuery(self, self._rows)

    def to_dataframe(self, include_metadata=False, pit_mode=False):
        return pd.DataFrame(self._rows)


def _row(
    concept,
    value,
    period_end,
    *,
    filing_date="2026-05-05",
    accession="0001628280-26-030584",
    period_type="instant",
    period_start=None,
    fiscal_period="Q1",
):
    return {
        "concept": concept,
        "label": concept,
        "numeric_value": value,
        "unit": "USD",
        "period_type": period_type,
        "period_start": period_start,
        "period_end": period_end,
        "fiscal_year": int(period_end[:4]),
        "fiscal_period": fiscal_period,
        "filing_date": filing_date,
        "form_type": "10-Q" if fiscal_period != "FY" else "10-K",
        "accession": accession,
        "statement_type": "BalanceSheet" if period_type == "instant" else "IncomeStatement",
        "data_quality": "high",
        "confidence_score": 1.0,
    }


def _oxy_facts():
    return FakeFacts(
        [
            _row(
                "LongTermDebtNoncurrent",
                23_351_000_000,
                "2025-12-31",
                filing_date="2026-02-18",
                accession="0001628280-26-012345",
                fiscal_period="FY",
            ),
            _row("LongTermDebtNoncurrent", 16_000_000_000, "2026-03-31"),
            _row("LongTermDebtCurrent", 611_000_000, "2026-03-31"),
            _row("CashAndCashEquivalentsAtCarryingValue", 1_200_000_000, "2026-03-31"),
            _row("StockholdersEquity", 35_000_000_000, "2026-03-31"),
            _row("AssetsCurrent", 8_000_000_000, "2026-03-31"),
            _row("LiabilitiesCurrent", 5_000_000_000, "2026-03-31"),
            _row("Assets", 80_464_000_000, "2026-03-31"),
            _row("Liabilities", 45_000_000_000, "2026-03-31"),
            _row("LongTermDebtTableTextBlock", 99_000_000_000, "2026-03-31"),
        ]
    )


def _cat_period_mismatch_facts():
    return FakeFacts(
        [
            _row("AssetsCurrent", 48_570_000_000, "2026-03-31"),
            _row("LiabilitiesCurrent", 35_900_000_000, "2026-03-31"),
            _row("Assets", 95_550_000_000, "2026-03-31"),
            _row("Liabilities", 76_890_000_000, "2026-03-31"),
            _row("StockholdersEquity", 18_660_000_000, "2026-03-31"),
            _row("CashAndCashEquivalentsAtCarryingValue", 4_080_000_000, "2026-03-31"),
            _row(
                "AssetsCurrent",
                50_000_000_000,
                "2025-12-31",
                filing_date="2026-02-13",
                accession="0000018230-26-000008",
                fiscal_period="FY",
            ),
            _row(
                "LiabilitiesCurrent",
                34_700_000_000,
                "2025-12-31",
                filing_date="2026-02-13",
                accession="0000018230-26-000008",
                fiscal_period="FY",
            ),
            _row(
                "CashAndCashEquivalentsAtCarryingValue",
                9_990_000_000,
                "2025-12-31",
                filing_date="2026-02-13",
                accession="0000018230-26-000008",
                fiscal_period="FY",
            ),
            _row(
                "StockholdersEquity",
                21_300_000_000,
                "2025-12-31",
                filing_date="2026-02-13",
                accession="0000018230-26-000008",
                fiscal_period="FY",
            ),
            _row(
                "ShortTermBorrowings",
                5_510_000_000,
                "2025-12-31",
                filing_date="2026-02-13",
                accession="0000018230-26-000008",
                fiscal_period="FY",
            ),
            _row(
                "LongTermDebtNoncurrent",
                30_700_000_000,
                "2025-12-31",
                filing_date="2026-02-13",
                accession="0000018230-26-000008",
                fiscal_period="FY",
            ),
            _row(
                "Revenues",
                17_410_000_000,
                "2026-03-31",
                period_type="duration",
                period_start="2026-01-01",
            ),
            _row(
                "OperatingIncomeLoss",
                3_085_000_000,
                "2026-03-31",
                period_type="duration",
                period_start="2026-01-01",
            ),
            _row(
                "ProfitLoss",
                2_548_000_000,
                "2026-03-31",
                period_type="duration",
                period_start="2026-01-01",
            ),
            _row(
                "NetIncomeLossAvailableToCommonStockholdersBasic",
                2_549_000_000,
                "2026-03-31",
                period_type="duration",
                period_start="2026-01-01",
            ),
            _row(
                "EarningsPerShareDiluted",
                5.47,
                "2026-03-31",
                period_type="duration",
                period_start="2026-01-01",
            ),
            _row(
                "NetIncomeLoss",
                1_141_000_000,
                "2011-09-30",
                filing_date="2011-11-04",
                accession="0001104659-11-060986",
                period_type="duration",
                period_start="2011-07-01",
            ),
        ]
    )


def _jpm_bank_debt_facts():
    return FakeFacts(
        [
            _row("Assets", 4_564_000_000_000, "2026-03-31", accession="0001628280-26-029344"),
            _row("Liabilities", 4_205_000_000_000, "2026-03-31", accession="0001628280-26-029344"),
            _row("StockholdersEquity", 359_000_000_000, "2026-03-31", accession="0001628280-26-029344"),
            _row(
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                312_138_000_000,
                "2026-03-31",
                accession="0001628280-26-029344",
            ),
            _row("ShortTermBorrowings", 68_048_000_000, "2026-03-31", accession="0001628280-26-029344"),
            _row(
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                448_764_000_000,
                "2026-03-31",
                accession="0001628280-26-029344",
            ),
        ]
    )


def test_edgar_balance_sheet_derives_current_period_debt(monkeypatch):
    facts = _oxy_facts()
    monkeypatch.setattr(edgar_fundamentals, "_load_company_facts", lambda ticker: facts)

    report = edgar_fundamentals.get_balance_sheet("OXY", curr_date="2026-05-13")

    assert "Total debt | $16.61B" in report
    assert "$23.35B" not in report.split("## Derived Debt And Liquidity", 1)[1]
    assert "2026-03-31" in report
    assert "2026-05-05" in report
    assert "0001628280-26-030584" in report
    assert "LongTermDebtCurrent" in report
    assert "LongTermDebtTableTextBlock" not in report
    assert facts.exact_flags
    assert all(facts.exact_flags)


def test_edgar_balance_sheet_keeps_snapshot_period_consistent(monkeypatch):
    facts = _cat_period_mismatch_facts()
    monkeypatch.setattr(edgar_fundamentals, "_load_company_facts", lambda ticker: facts)

    report = edgar_fundamentals.get_balance_sheet("CAT", curr_date="2026-05-12")

    assert "Latest balance sheet snapshot period is 2026-03-31" in report
    assert "Total debt | $36.21B" in report
    assert "Current ratio | 1.35" in report
    assert "Current ratio | 1.35 | Current assets, Current liabilities | 2026-03-31" in report

    reported_facts = report.split("## Reported Facts - Period-Consistent Snapshot", 1)[1]
    assert "Current assets | $48.57B | as of 2026-03-31" in reported_facts
    assert "Short-term debt" not in reported_facts
    assert "Long-term debt" not in reported_facts


def test_edgar_balance_sheet_uses_combined_long_term_debt_for_banks(monkeypatch):
    facts = _jpm_bank_debt_facts()
    monkeypatch.setattr(edgar_fundamentals, "_load_company_facts", lambda ticker: facts)

    report = edgar_fundamentals.get_balance_sheet("JPM", curr_date="2026-05-12")

    assert "Total debt | $516.81B" in report
    assert "Net debt | $204.67B" in report
    assert "Long-term debt incl. current maturities" in report
    assert "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities" in report


def test_edgar_income_statement_omits_stale_net_income_when_current_concept_exists(monkeypatch):
    facts = _cat_period_mismatch_facts()
    monkeypatch.setattr(edgar_fundamentals, "_load_company_facts", lambda ticker: facts)

    report = edgar_fundamentals.get_income_statement("CAT", curr_date="2026-05-12")

    assert "Reported facts are anchored to period end 2026-03-31" in report
    assert "Net income | $2.55B | 90D ended 2026-03-31" in report
    assert "NetIncomeLossAvailableToCommonStockholdersBasic" in report
    assert "2011-09-30" not in report
    assert "$1.14B" not in report


def test_route_to_vendor_falls_back_when_edgar_unavailable(tmp_path, monkeypatch):
    config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config["data_cache_dir"] = str(tmp_path)
    config["data_vendors"]["fundamental_data"] = "edgar,yfinance"
    config["data_tool_cache_enabled"] = True
    set_config(config)
    interface._CACHE_LOCKS.clear()

    calls = {"edgar": 0, "yfinance": 0}

    def edgar_impl(ticker, curr_date):
        calls["edgar"] += 1
        raise DataVendorUnavailableError("SEC blocked")

    def yfinance_impl(ticker, curr_date):
        calls["yfinance"] += 1
        return f"fallback fundamentals for {ticker} on {curr_date}"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_fundamentals"], "edgar", edgar_impl)
    monkeypatch.setitem(interface.VENDOR_METHODS["get_fundamentals"], "yfinance", yfinance_impl)

    result = interface.route_to_vendor("get_fundamentals", "OXY", "2026-05-13")

    assert result == "fallback fundamentals for OXY on 2026-05-13"
    assert calls == {"edgar": 1, "yfinance": 1}


def test_gluetun_proxy_url_can_be_loaded_from_ignored_env_file(tmp_path):
    env_file = tmp_path / "gluetun.env"
    env_file.write_text(
        "\n".join(
            [
                "GLUETUN_BIND_IP=100.111.132.114",
                "HTTPPROXY_USER=proxy user",
                "HTTPPROXY_PASSWORD=p@ss word",
            ]
        ),
        encoding="utf-8",
    )

    proxy_url = edgar_fundamentals._gluetun_proxy_from_env_file(str(env_file))

    assert proxy_url == "http://proxy%20user:p%40ss%20word@100.111.132.114:8888"
