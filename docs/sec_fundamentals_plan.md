# SEC Fundamentals Plan

This plan covers the debt-number fix and the supporting SEC/Gluetun plumbing.
The goal is to make SEC filings the source of truth for statement fundamentals,
while keeping yfinance for market data, valuation fields, and price history.

## Current Findings

- The local `edgartools` fork lives at `/home/ade/Projects/edgartools`.
- The fork exposes exact concept filtering through `FactQuery.by_concept(..., exact=True)`.
- `EntityFacts.to_dataframe(..., pit_mode=True)` can preserve filing date, form type,
  accession, and period metadata for point-in-time runs.
- Nearby `market-intel-workbench` code already maps common debt concepts and derives
  `total_debt` from short-term debt, current debt, and long-term debt.
- The local Gluetun container is running and healthy.
- Gluetun's authenticated HTTP proxy works for general traffic through
  `100.111.132.114:8888`.
- The current Gluetun exit IP still receives SEC HTTP 403 responses from
  `data.sec.gov`, so VPN routing needs fallback and possibly IP rotation.

## Implementation Status

- Added the local `edgartools` fork as a `uv` editable path dependency.
- Added SEC identity, proxy, Gluetun, and prefetch config/env support.
- Added an `edgar` fundamentals vendor with yfinance fallback.
- Added exact-concept SEC debt derivation with source metadata.
- Added optional Gluetun Docker profile support.
- Removed premature final-decision instructions from analyst prompts.
- Added deterministic cache-warming prefetch support.
- Added fixture tests for the OXY-style debt-period regression and fallback path.

## Principles

- Do not cache blocked SEC responses or other transient network errors.
- Do not commit Gluetun credentials or proxy URLs containing credentials.
- Keep SEC fundamentals deterministic before handing them to the LLM.
- Keep every reported value tied to source metadata: concept, period end,
  filing date, form type, and accession.
- Do not mix facts from different fiscal periods when deriving ratios or totals.

## Phase 1: SEC And Gluetun Plumbing

1. Add a local `edgartools` dependency with `uv`, preferably as a path dependency
   while using the local fork.
2. Add config/env support for SEC access:
   - `TRADINGAGENTS_SEC_IDENTITY`
   - `TRADINGAGENTS_SEC_PROXY_URL`
   - `TRADINGAGENTS_SEC_USE_GLUETUN`
3. For host `uv run` workflows, support the authenticated Gluetun proxy through
   `TRADINGAGENTS_SEC_PROXY_URL` or standard `HTTP_PROXY` / `HTTPS_PROXY`.
4. For Docker workflows, add an optional service/profile that runs TradingAgents
   with `network_mode: "container:gluetun"`.
5. Add SEC network error handling:
   - 403 or proxy auth failure marks SEC as unavailable for that call.
   - SEC unavailable falls back to the next configured vendor.
   - Errors are returned with enough detail for logs, but not cached as valid data.

## Phase 2: SEC Fundamentals Vendor

1. Add `tradingagents/dataflows/edgar_fundamentals.py`.
2. Register an `edgar` vendor in `tradingagents/dataflows/interface.py`.
3. Support these existing tool surfaces:
   - `get_fundamentals`
   - `get_balance_sheet`
   - `get_cashflow`
   - `get_income_statement`
4. Use exact SEC concepts for statement extraction.
5. Select only facts available as of `curr_date`.
6. Return compact Markdown tables instead of wide raw CSV where possible.

## Phase 3: Debt And Liquidity Derivations

1. Build a concept registry for debt components:
   - short-term borrowings
   - current portion of long-term debt
   - long-term debt, noncurrent
   - cash and equivalents
   - stockholders' equity
2. Select all debt components from the same latest instant period.
3. Compute:
   - `total_debt`
   - `net_debt`
   - `debt_to_equity`
   - `current_ratio`, when current assets and current liabilities are present
4. Include the component table under every derived figure.
5. Keep management-stated principal debt separate from balance sheet total debt
   if we later extract it from filing text or earnings releases.

## Phase 4: Prompt And Flow Cleanup

1. Update the fundamentals analyst prompt to require source dates and filing
   metadata for SEC-derived numbers.
2. Remove premature `FINAL TRANSACTION PROPOSAL` language from analyst prompts;
   analysts should analyze, not produce the final action.
3. Prefer deterministic prefetch of fundamentals before LLM calls once the SEC
   vendor is stable.
4. Keep yfinance fundamentals as fallback, but label it clearly when used.

## Phase 5: Tests

1. Add fixture-based tests for SEC fact selection and debt derivation.
2. Include an OXY-style regression test that prevents mixing `2025-12-31` debt
   with `2026-03-31` statement data.
3. Mock `edgartools` calls so tests do not require live SEC access.
4. Add a routing test that confirms `edgar,yfinance` falls back cleanly when SEC
   returns unavailable.
5. Add config/env tests for the new SEC and proxy settings.

## Phase 6: Remaining Speed Work

1. Implement deterministic data prefetch before analyst LLM calls.
2. Trim analyst prompts and report targets.
3. Add node-level run timing, model name, and tool-call counts to CLI logs.
4. Benchmark fast, balanced, and quality profiles against the same ticker/date.
5. Revisit checkpointing after the serialization fix has been exercised through
   a complete local Ollama run.

## Acceptance Criteria

- OXY's fundamentals report no longer reports a stale yfinance debt value as
  current-quarter debt.
- Debt numbers include period end, filing date, accession, and component concepts.
- A blocked SEC request does not poison the tool-result cache.
- Local runs can opt into Gluetun routing without committing secrets.
- Existing yfinance and Alpha Vantage paths keep working.
- The full test suite passes under `uv run pytest`.
