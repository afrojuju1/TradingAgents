# TradingAgents Robustness Roadmap

Last updated: 2026-05-13

This roadmap groups the remaining system improvements into implementation
chunks. The priority is to make TradingAgents more deterministic, easier to
verify, faster on local Ollama, and less prone to unsupported claims in final
reports.

## Current Baseline

Already landed:

- Deterministic market summary tool for OHLCV, range, return, volume,
  volatility, drawdown, RSI, MACD, and 50/200 SMA.
- Deterministic fundamentals summary tool for SEC-derived balance sheet,
  income, cash flow, leverage, liquidity, bank/financial accounting context,
  and asset/liability relationship checks.
- First-pass durable fact artifacts: `market_facts.json`,
  `fundamental_facts.json`, `valuation_facts.json`, `event_facts.json`,
  `news_sources.json`, `sentiment_facts.json`, `data_tool_events.json`, and
  `claim_checks.json`.
- First-pass numeric report proof checks for market technicals and
  fundamentals contradictions.
- Deterministic news source extraction and sentiment source statistics.
- Analyst parallelism, tool-result caching, prefetch support, local Ollama
  run profiles, SEC EdgarTools integration, Gluetun support, report quality
  pattern checks, and checkpoint metadata serialization fixes.
- Structured-output recovery for local/Ollama models: raw tool-call payloads
  are normalized and validated through Pydantic schemas before markdown
  rendering, avoiding free-text retries for small enum/object shape issues.
- Derived total-liabilities support when SEC statements provide assets and
  equity but omit a direct liabilities concept, plus tighter prompt wording
  around unavailable peer benchmarks.

## Milestone 1: Proofable Reports

Goal: every generated report should be checkable against deterministic facts.

### Chunk 1.1: Durable Fact Artifacts

Write normalized facts beside every run:

- `market_facts.json`
- `fundamental_facts.json`
- `news_sources.json`
- `sentiment_facts.json`
- `claim_checks.json`

Done when:

- Each analyst fact pack is persisted under the report directory.
- Artifacts include source, observed date, retrieved date, normalized value,
  and freshness metadata.
- Report review can use JSON artifacts without re-parsing generated prose.

### Chunk 1.2: Numeric Report Proof Checks

Extend `tradingagents.report_quality` beyond pattern checks.

Checks to add:

- Prices, highs/lows, returns, RSI, SMA, MACD, volume, volatility, and
  drawdown must match `market_facts.json`.
- Assets, liabilities, equity, debt, net debt, EPS, net income, operating cash
  flow, and free cash flow must match `fundamental_facts.json`.
- Asset/liability relationship claims must match deterministic relationships.
- Bank/financial cash-flow guardrails must appear when relevant.

Done when:

- `scripts/check_report_quality.py` fails on unsupported numeric claims.
- JPM-style failures such as fake low prices, wrong RSI, and "liabilities
  exceed assets" are caught automatically.

### Chunk 1.3: Claim Registry

Add a lightweight claim model:

- `claim_id`
- `claim_text`
- `claim_type`
- `source_fact_ids`
- `normalized_values`
- `confidence`
- `status`: supported, unsupported, contradicted, stale, or unverified

Done when:

- Final reports can be traced from prose claims back to source facts.
- Unsupported claims are listed in `claim_checks.json`.

## Milestone 2: News and Sentiment Grounding

Goal: stop macro/news/sentiment hallucinations at the source.

### Chunk 2.1: News Source Extraction

Parse news tool output into source records:

- Title
- Publisher
- URL
- Published date
- Retrieved date
- Ticker or macro query
- Capped summary

Done when:

- News analyst gets a compact `news_sources` pack instead of loose raw text.
- Every cited news item has a stable source ID.

### Chunk 2.2: News Claim Gating

Require every material news claim to cite a source ID.

Claims to gate:

- CPI, inflation, rates, Fed/central-bank policy
- Oil, commodities, currencies
- Dividends, yields, market cap, AUM, M&A, price targets
- Company-specific catalysts and risks

Done when:

- Macro numbers not present in `news_sources.json` are flagged.
- News analyst cannot invent CPI, Brent, Fed hike, dividend, or AUM figures
  without detection.

### Chunk 2.3: News Relevance Filtering

Score global and company news before the LLM sees it.

Signals:

- Ticker/company name match
- Sector match
- Recency
- Source quality
- Macro relevance to the ticker
- Duplicate headline clustering

Done when:

- Irrelevant broad headlines are filtered or labeled low relevance.
- News prompts are shorter and less noisy.

### Chunk 2.4: Sentiment Fact Pack

Make sentiment deterministic before the LLM writes.

Facts to derive:

- StockTwits bullish/bearish/no-label counts
- Reddit post count, total score, total comments, top posts
- News sentiment counts by headline classification
- Source availability and sample-size warnings

Done when:

- Sentiment report cites deterministic counts and availability warnings.
- Small samples are clearly marked low confidence.

## Milestone 3: Downstream Agent Grounding

Goal: prevent researchers, risk debaters, and final decision agents from
introducing unsupported numbers after analysts did the right thing.

### Chunk 3.1: Structured Analyst Memos

Move analyst outputs toward structured JSON plus rendered markdown.

Fields:

- Summary
- Key facts
- Claims
- Evidence IDs
- Caveats
- Confidence
- Unsupported gaps

Done when:

- Research and risk agents can consume compact structured memos.
- Markdown remains available for human reports.

### Chunk 3.2: Debate Grounding

Feed bull, bear, and risk agents fact packs, not only analyst prose.

Rules:

- New numeric claims must cite an existing fact or source ID.
- AUM, price-target, macro, valuation, and rally-percentage claims are blocked
  or flagged unless supported.
- Bull/bear/risk arguments must distinguish evidence from speculation.

Done when:

- Debate stages no longer amplify unsupported analyst wording into stronger
  unsupported claims.

### Chunk 3.3: Final Decision Grounding

Add deterministic checks before Portfolio Manager output is accepted.

Checks:

- Final rating must be one allowed rating.
- Final reasoning must cite analyst/fact evidence.
- Contradictions against fact packs are flagged.
- Missing critical evidence is listed as residual risk.

Done when:

- Final decision quality can be evaluated without manually reading the full
  report.

## Milestone 4: Prepared-Data Execution

Goal: reduce local Ollama wall time and tool-loop variance.

### Chunk 4.1: Prepared Analyst Mode

Build selected data payloads before analyst prompts and run selected analysts
without tool binding when possible.

Targets:

- Market analyst
- Fundamentals analyst
- News analyst
- Sentiment analyst

Done when:

- Analysts can run from prepared fact/source packs.
- Tool loops are optional for analysts with prepared data.
- Prompt payloads are compact and capped.

### Chunk 4.2: Prompt and Report Budgets

Add explicit output budgets.

Controls:

- Max sections per agent
- Max bullets per section
- Max words or tokens per report
- Required concise summary table
- No repeated generic instructions

Done when:

- Token usage drops materially from the JPM baseline.
- Reports remain decision-useful without long repetitive prose.

### Chunk 4.3: Parallel First-Round Risk Debate

Run aggressive, neutral, and conservative first-round risk opinions in parallel.

Done when:

- First risk round uses the same trader state for all three agents.
- A merge step collects the three opinions before any response round.
- Local Ollama speed improves without changing final decision semantics.

## Milestone 5: Operations and Observability

Goal: make runs repeatable, measurable, resumable, and easier to debug.

### Chunk 5.1: Benchmark Harness

Create a reusable non-interactive benchmark command.

Record:

- Ticker
- Trade date
- Run profile
- Model names
- Wall time
- Node timings
- Tool timings
- LLM call counts
- Token usage
- Cache hit/miss counts
- Report quality result
- GPU/model residency snapshot when available

Done when:

- Fast, balanced, and quality profiles can be compared on the same ticker.
- Performance regressions are easy to spot.

### Chunk 5.2: Checkpoint Full-Run Validation

Validate checkpointing through full local Ollama runs.

Checks:

- Resume after interruption.
- SQLite files stay bounded.
- Checkpoint serialization does not fail on message metadata.
- Resume does not duplicate report sections or tool calls.

Done when:

- Checkpointing can be safely enabled for long local runs.

### Chunk 5.3: Provider Health and Fallback Reporting

Make provider failures visible.

Record:

- Primary vendor attempted
- Fallback vendor used
- Error type
- Proxy/Gluetun state for SEC calls
- Cache state
- Freshness age

Done when:

- Reports and metadata show when data came from fallback or stale cache.
- Quality checks can fail or warn on low-confidence data provenance.

### Chunk 5.4: Multi-Ticker Batch Runner

Add a batch runner tuned for local Ollama.

Features:

- Queue symbols with max concurrent runs.
- Respect `OLLAMA_NUM_PARALLEL`.
- Avoid loading too many models at once.
- Reuse warm cache and resident models.
- Save per-symbol timing and quality results.

Done when:

- Multi-symbol scans are faster than manual one-off runs and do not overload
  Ollama or SEC/news vendors.

## Milestone 6: Finance Data Robustness and Domain Coverage

Goal: make finance facts typed, provenance-aware, and fit for different
company types.

### Chunk 6.1: Typed Finance Fact Schemas

Move finance artifacts from plain dictionaries to validated Pydantic models.

Schemas:

- `MarketFacts`
- `FundamentalFacts`
- `ValuationFacts`
- `EventFacts`
- `DataToolEvent`

Done when:

- Fact payloads are validated before being rendered, saved, or passed to an
  agent.
- Schema validation catches missing required source/provenance fields.
- Report-quality checks consume typed facts instead of defensive dict access.

### Chunk 6.2: Strict Vendor Failure Semantics

Normalize data-vendor failure behavior before fallback routing.

Current issue:

- Some vendors raise typed exceptions, but several yfinance paths return
  strings such as `Error retrieving...` or `No data found...`. Those strings
  can be recorded as errors while still flowing downstream as low-quality tool
  text.

Done when:

- Empty, unavailable, rate-limited, and malformed vendor responses become
  typed errors.
- `route_to_vendor` only returns successful, parseable payloads.
- Fallback metadata records every attempted vendor and the final selected
  vendor.
- Reports can warn or fail when only fallback or low-confidence data was
  available.

### Chunk 6.3: Point-in-Time Labels for Snapshot Data

Make freshness and look-ahead risk explicit for every finance data source.

Scope:

- SEC statement facts are already filing-date/as-of aware.
- OHLCV is filtered to the trade date.
- yfinance `info` and `calendar` are current snapshots and should be labeled
  as such when used for historical trade dates.

Done when:

- Every fact has `observed_at`, `retrieved_at`, `as_of`, and
  `point_in_time_safe` metadata where applicable.
- Backtest runs can disable current-snapshot valuation/event data or mark it
  as lower confidence.
- Report quality can warn when a historical run used present-day snapshot
  data.

### Chunk 6.4: Sector Accounting Context Expansion

Extend fundamentals context beyond banks.

Contexts:

- Banks and financials
- Insurers
- REITs
- Energy
- Capital-intensive industrials
- Software/SaaS
- Retail
- Semiconductors

Done when:

- Each context has metric interpretation guardrails.
- Generic industrial assumptions are not applied to sector-specific statements.

### Chunk 6.5: Valuation Fact Pack

Expand deterministic valuation inputs.

Inputs:

- Market cap
- Enterprise value
- P/E
- Forward P/E
- Price/book
- Dividend yield
- Buyback yield when available
- EV/sales, EV/EBITDA, PEG, earnings yield, and free-cash-flow yield when
  sourceable
- Sector or peer benchmark valuations when sourceable and clearly labeled

Done when:

- Valuation claims come from a normalized source, not free-text inference.
- Missing valuation fields produce explicit guardrails instead of vague prose.
- Peer comparisons cite an explicit peer/sector source and date.

### Chunk 6.6: Event Calendar Pack

Expand deterministic upcoming-event context.

Events:

- Earnings date
- Ex-dividend date
- Major filing date
- Investor day
- Product/regulatory events when sourceable
- Conference presentations and guidance updates when sourceable
- Dividend declaration, record, and payment dates when sourceable

Done when:

- Catalyst timing is explicit and source-backed.
- Event fields are labeled as company calendar, exchange calendar, SEC filing,
  or external news/event source.

### Chunk 6.7: Dividend, Buyback, and Share-Count Pack

Add deterministic capital-return and dilution context.

Inputs:

- Declared dividend and yield
- Ex-dividend, record, and payment dates
- Dividend payout versus earnings and free cash flow
- Share repurchases
- Weighted average diluted shares
- Share count change over time
- Net buyback yield when sourceable

Done when:

- Reports can distinguish income yield from total capital return.
- Dilution or buyback claims are grounded in saved facts.
- Dividend safety claims cite payout and free-cash-flow coverage.

### Chunk 6.8: Debt Service and Maturity Pack

Add deterministic solvency facts beyond total debt.

Inputs:

- Interest expense
- EBIT or operating income
- Interest coverage
- Current debt versus long-term debt
- Debt maturity schedule when parseable
- Cash and marketable securities
- Net debt / EBITDA when sourceable

Done when:

- Debt-risk claims use coverage and maturity facts, not only absolute debt.
- Rate-sensitivity claims are blocked unless fixed/floating or maturity data
  is available.

### Chunk 6.9: Expectations and Revision Pack

Add forward-looking estimate context without letting it become unsupported
forecasting.

Inputs:

- Forward EPS and revenue estimates
- Estimate high/low/average
- Recent estimate revisions
- Earnings surprise history
- Guidance ranges when sourceable

Done when:

- Earnings setup claims distinguish reported facts from analyst expectations.
- Estimate numbers cite a source and date.
- Missing estimate data produces explicit guardrails.

### Chunk 6.10: Market Microstructure and Positioning Pack

Add optional risk/positioning facts for trade setup quality.

Inputs:

- Short interest and days to cover
- Options implied volatility
- Put/call ratio or skew when sourceable
- Major open-interest strikes
- Average dollar volume and liquidity
- Institutional and insider activity when sourceable

Done when:

- Crowding, squeeze, liquidity, and options-risk claims are either supported
  or blocked.
- These facts remain optional and do not slow the default fast profile unless
  enabled.

## Milestone 7: Repo and Report Hygiene

Goal: keep the workspace clean and output handling intentional.

### Chunk 7.1: Report Ignore or Archive Policy

Decide how generated reports are tracked.

Options:

- Ignore `reports/` entirely.
- Track selected golden reports under `tests/fixtures/reports/`.
- Add a command to archive reports into a dated local folder outside the repo.

Done when:

- Normal runs do not leave noisy untracked report directories.
- Intentional golden reports are clearly separated from local output.

### Chunk 7.2: Golden Report Regression Fixtures

Keep a small set of representative report fixtures.

Suggested fixtures:

- Bank: JPM
- Energy: OXY
- Industrial: CAT
- Tech/semiconductor: AMD or NVDA

Done when:

- Quality checks run against known historical failure modes.
- Future changes cannot silently reintroduce the old deterministic mistakes.

## Suggested Execution Order

1. Typed finance fact schemas.
2. Strict vendor failure semantics.
3. Point-in-time labels for snapshot data.
4. Durable fact artifacts.
5. Numeric report proof checks.
6. News source extraction.
7. News claim gating.
8. Debate grounding.
9. Prepared-data analyst mode.
10. Prompt/report budgets.
11. Benchmark harness.
12. Parallel first-round risk debate.
13. Checkpoint full-run validation.
14. Valuation/event pack expansion.
15. Dividend, buyback, share-count, and debt-service packs.
16. Expectations/revisions and market-positioning packs.
17. Sector accounting context expansion.
18. Multi-ticker batch runner.
19. Golden report fixtures and report archive policy.

The first three chunks should come first because they make every future fact
pack validated, provenance-aware, and honest about fallback or snapshot data.
After that, report proof checks, news grounding, and debate grounding attack
quality directly, while prepared-data mode and prompt budgets attack runtime.
