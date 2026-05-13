# Finance Data Inventory

Last updated: 2026-05-13

This document inventories the finance data TradingAgents currently gathers or
should gather for grounded equity analysis. It is intentionally written for
review: each data point lists why it matters, where it comes from today, and
what caveats remain.

Out of scope for this file: general macro/news/sentiment data except where it
directly supports a company finance fact, event, or catalyst.

## Data Flow

Current intended flow:

1. Vendor tools fetch raw data.
2. Deterministic parsers normalize raw data into compact fact packs.
3. Fact packs are rendered into analyst prompts and saved as JSON artifacts.
4. Agents write prose from the fact packs.
5. Report-quality checks compare generated prose back to saved facts.

Key artifacts:

- `market_facts.json`
- `fundamental_facts.json`
- `valuation_facts.json`
- `event_facts.json`
- `data_tool_events.json`

Each finance fact should eventually carry:

- `metric`
- `label`
- `value`
- `numeric_value`
- `unit`
- `source`
- `observed_at` or `period_end`
- `retrieved_at`
- `as_of`
- `vendor`
- `filing_date`, `form`, `accession`, and `concept` for SEC-derived facts
- `point_in_time_safe`
- `confidence` or `data_quality_warnings`

## Current Market Data

Source today: yfinance OHLCV plus stockstats-derived indicators.

Artifact today: `market_facts.json`.

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Latest open, high, low, close | Anchors current price action and entry/stop references. | Gathered and checked. |
| First close in analysis window | Needed to compute window return without LLM math. | Gathered. |
| Window close return | Gives trend magnitude over the configured lookback. | Derived. |
| Window high and low | Frames broad range and drawdown context. | Derived. |
| Recent support low | Provides grounded stop/support level candidates. | Derived from last 30 rows. |
| Recent resistance high | Provides grounded resistance/target discussion. | Derived from last 30 rows. |
| Latest volume | Detects participation and liquidity at current price. | Gathered. |
| 30-row average volume | Baseline for volume confirmation or weakness. | Derived. |
| Latest volume / average volume | Prevents vague volume claims. | Derived. |
| Annualized volatility | Provides risk and sizing context. | Derived from daily returns. |
| Max drawdown | Gives downside behavior over the analysis window. | Derived. |
| 50-day SMA | Medium-term trend and support/resistance context. | Gathered through indicator path. |
| 200-day SMA | Long-term trend context. | Gathered through indicator path. |
| RSI | Momentum/overbought/oversold context. | Gathered through indicator path. |
| MACD | Trend momentum confirmation. | Gathered through indicator path. |

Market data improvements to consider:

- Average dollar volume for liquidity sizing.
- ATR for volatility-aware stop distance.
- Bollinger bands for range/volatility context.
- 10/20-day realized volatility for short-term risk.
- Gap from 52-week high/low as deterministic percentages.
- Benchmark-relative return versus SPY or regional benchmark.

## Current SEC Fundamentals

Primary source today: SEC EDGAR via edgartools.

Fallback source today: yfinance or Alpha Vantage, depending on vendor config.

Artifact today: `fundamental_facts.json`.

### Balance Sheet

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Cash and equivalents | Liquidity, net debt, downside resilience. | Gathered when reported. |
| Current assets | Short-term liquidity and current ratio. | Gathered when reported. |
| Current liabilities | Short-term obligations and current ratio. | Gathered when reported. |
| Total assets | Balance-sheet scale and asset/liability relationship. | Gathered. |
| Total liabilities | Solvency and leverage context. | Gathered or derived from assets minus equity when needed. |
| Stockholders' equity | Debt/equity, book value context, and derived liabilities. | Gathered. |
| Short-term debt | Near-term refinancing pressure. | Gathered when reported. |
| Current debt | Near-term debt maturity pressure. | Gathered when reported. |
| Long-term debt | Longer-term leverage. | Gathered when reported. |
| Long-term debt including current maturities | Common single debt concept for some issuers. | Gathered when reported. |

### Derived Debt and Liquidity

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Total debt | Baseline leverage measure. | Derived from same-period debt components. |
| Net debt | Debt adjusted for cash resources. | Derived when cash is available. |
| Debt-to-equity | Simple leverage ratio; useful but sector-sensitive. | Derived when equity is available. |
| Current ratio | Short-term liquidity for non-financial companies. | Derived from same-period current assets/liabilities. |
| Assets minus liabilities | Prevents asset/liability contradiction in prose. | Derived. |
| Liabilities/assets | Helps classify financial-company balance sheets. | Derived when liabilities are available. |
| Equity/assets | Balance-sheet capitalization context. | Derived. |
| Accounting context | Prevents applying industrial metrics to banks/financials. | First-pass heuristic exists. |

### Income Statement

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Revenue | Growth and business scale. | Gathered. |
| Gross profit | Pricing power and cost structure. | Gathered when reported. |
| Operating income | Core profitability and interest coverage input. | Gathered when reported. |
| Pretax income | Tax/interest bridge context. | Gathered when reported. |
| Net income | Bottom-line profitability. | Gathered. |
| Diluted EPS | Per-share earnings anchor. | Gathered when reported. |

### Cash Flow and Capital Allocation

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Operating cash flow | Cash earnings quality and dividend/debt support. | Gathered. |
| Capital expenditures | Reinvestment and free cash flow calculation. | Gathered when reported. |
| Free cash flow | Dividend, buyback, and debt-service capacity. | Derived. |
| Dividends paid | Cash capital return and payout pressure. | Gathered when reported. |
| Share repurchases | Capital return and share-count support. | Gathered when reported. |

SEC fundamentals improvements to consider:

- Interest expense and interest coverage.
- EBITDA or adjusted EBITDA where sourceable.
- Net debt / EBITDA where sourceable.
- Debt maturity schedule.
- Segment revenue and operating income.
- Geographic revenue.
- Margins: gross, operating, net, and FCF margin.
- Return metrics: ROE, ROA, ROIC when sourceable.
- Working capital change.
- Deferred revenue for software/SaaS.
- Inventory and receivables quality for retail/industrial companies.

## Current Valuation Data

Source today: yfinance `info`.

Artifact today: `valuation_facts.json`.

Important caveat: yfinance `info` is a current snapshot. For historical
backtests, these fields should be labeled `point_in_time_safe=false` unless
replaced with an as-of-safe source.

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Market cap | Equity valuation scale. | Gathered. |
| Enterprise value | Capital-structure-adjusted valuation scale. | Gathered. |
| Trailing P/E | Market multiple on reported earnings. | Gathered when available. |
| Forward P/E | Expectations-based earnings valuation. | Gathered when available. |
| Price/book | Balance-sheet valuation context. | Gathered when available. |
| Dividend yield | Income return anchor. | Gathered when available. |
| Beta | Market sensitivity and risk context. | Gathered when available. |
| 52-week high | Price range context. | Gathered. |
| 52-week low | Price range context. | Gathered. |
| 50-day average | Valuation/market context duplicate of technical trend. | Gathered. |
| 200-day average | Long-term trend context duplicate of technical trend. | Gathered. |

Valuation improvements to consider:

- EV/sales.
- EV/EBITDA.
- EV/EBIT.
- Price/sales.
- PEG ratio.
- Earnings yield.
- Free-cash-flow yield.
- Dividend payout ratio.
- Buyback yield.
- Total shareholder yield.
- Peer or sector benchmark medians when sourceable.
- Historical multiple ranges for the same company.

## Current Event Data

Source today: yfinance calendar.

Artifact today: `event_facts.json`.

Important caveat: calendar fields are current snapshots. For historical
backtests, these fields should be labeled `point_in_time_safe=false` unless
the event source is as-of-safe.

| Data point | Why it is needed | Current status |
| --- | --- | --- |
| Earnings date | Near-term catalyst and timing risk. | Gathered when yfinance exposes it. |
| Earnings estimate high/low/average | Expectations range for the next report. | Parsed when present. |
| Revenue estimate high/low/average | Sales expectations range for the next report. | Parsed when present. |
| Ex-dividend date | Dividend timing and price-adjustment context. | Gathered when present. |
| Dividend payment date | Income timing. | Gathered when present. |

Event improvements to consider:

- SEC filing due dates and actual filing dates.
- Dividend declaration and record dates.
- Investor days.
- Guidance update dates.
- Conference presentations.
- Product or regulatory events when sourceable.
- Corporate actions: splits, spin-offs, tender offers, major M&A.

## Additional Finance Packs Worth Adding

### Analyst Expectations and Revisions

Needed data:

- Forward EPS estimate.
- Forward revenue estimate.
- Estimate high, low, and average.
- Recent estimate revisions.
- Earnings surprise history.
- Company guidance range where sourceable.

Why it matters:

- Separates reported facts from market expectations.
- Grounds claims about earnings setup, beat/miss risk, and valuation support.
- Reduces unsupported "guidance" and "consensus" claims.

### Dividend, Buyback, and Share Count

Needed data:

- Declared dividend.
- Dividend frequency.
- Dividend payout versus net income.
- Dividend payout versus free cash flow.
- Share repurchases.
- Weighted average diluted shares.
- Current shares outstanding.
- Share-count change over time.
- Net buyback yield when sourceable.

Why it matters:

- Dividend safety needs payout and FCF coverage, not just yield.
- Buybacks matter only if they reduce share count or offset dilution.
- Per-share value creation depends on dilution and repurchases.

### Debt Service and Maturity

Needed data:

- Interest expense.
- EBIT or operating income.
- Interest coverage.
- Current debt.
- Long-term debt.
- Debt maturities by year.
- Fixed versus floating-rate debt when sourceable.
- Cash, cash equivalents, and marketable securities.

Why it matters:

- Absolute debt is incomplete without service capacity and maturity timing.
- Rate-risk claims require maturity or fixed/floating evidence.
- Refinancing risk is a timing issue, not only a balance-sheet issue.

### Market Positioning and Liquidity

Needed data:

- Average dollar volume.
- Short interest.
- Days to cover.
- Float.
- Options implied volatility.
- Put/call ratio or skew.
- Major open-interest strikes.

Why it matters:

- Position sizing needs liquidity context.
- Short-squeeze and crowding claims need short-interest evidence.
- Options risk and event premium need IV/skew evidence.

### Insider and Institutional Activity

Needed data:

- Insider buys and sells.
- Insider ownership.
- Institutional ownership.
- Recent 13F changes when sourceable.
- Large holder concentration.

Why it matters:

- Insider/institutional claims are often hallucinated unless explicitly
  grounded.
- Ownership concentration can affect liquidity, governance, and volatility.

### Segment and Geography Detail

Needed data:

- Segment revenue.
- Segment operating income or margin.
- Geography revenue.
- Customer concentration where disclosed.

Why it matters:

- Segment mix explains growth, margin, and cyclicality.
- Geography mix grounds FX, tariff, China, EU, or emerging-market claims.
- Customer concentration changes risk profile.

## Minimum Required Fact Contract

Before a finance fact is allowed into an agent prompt, it should answer:

- What is the metric?
- What is the value?
- What is the unit?
- What date or period does it describe?
- When was it retrieved?
- Which vendor/source produced it?
- Is it point-in-time safe for the trade date?
- Is it reported, derived, estimated, or current snapshot?
- Which components were used if derived?
- What caveats should an agent preserve?

If a fact cannot answer these questions, it should either be excluded from the
default prompt or included only with explicit low-confidence guardrails.

## Review Priorities

Recommended next review order:

1. Approve the fact contract fields.
2. Convert current artifacts to Pydantic schemas.
3. Make vendor failures typed instead of string-shaped.
4. Add point-in-time labels to yfinance valuation and calendar facts.
5. Decide which new finance packs matter most for the first enrichment pass:
   dividend/share count, debt service, expectations/revisions, or
   market positioning.
