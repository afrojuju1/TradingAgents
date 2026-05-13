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
- Analyst parallelism, tool-result caching, prefetch support, local Ollama
  run profiles, SEC EdgarTools integration, Gluetun support, report quality
  pattern checks, and checkpoint metadata serialization fixes.

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

## Milestone 6: Domain Coverage

Goal: make deterministic interpretation fit different company types.

### Chunk 6.1: Sector Accounting Context Expansion

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

### Chunk 6.2: Valuation Fact Pack

Add deterministic valuation inputs.

Inputs:

- Market cap
- Enterprise value
- P/E
- Forward P/E
- Price/book
- Dividend yield
- Buyback yield when available
- Sector peer medians where available

Done when:

- Valuation claims come from a normalized source, not free-text inference.

### Chunk 6.3: Event Calendar Pack

Add deterministic upcoming-event context.

Events:

- Earnings date
- Ex-dividend date
- Major filing date
- Investor day
- Product/regulatory events when sourceable

Done when:

- Catalyst timing is explicit and source-backed.

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

1. Durable fact artifacts.
2. Numeric report proof checks.
3. News source extraction.
4. News claim gating.
5. Debate grounding.
6. Prepared-data analyst mode.
7. Prompt/report budgets.
8. Benchmark harness.
9. Parallel first-round risk debate.
10. Checkpoint full-run validation.
11. Sector accounting context expansion.
12. Multi-ticker batch runner.
13. Golden report fixtures and report archive policy.

The first two chunks should come first because they turn every future run into
a measurable regression test. After that, news grounding and debate grounding
attack the remaining quality issues directly, while prepared-data mode and
prompt budgets attack runtime.
