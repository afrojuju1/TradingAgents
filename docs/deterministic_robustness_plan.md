# Deterministic Robustness Plan

This tracks the remaining places where TradingAgents should prefer parsed,
normalized facts over model-interpreted raw text. The inspiration is the
neighboring `market-intel-workbench` pattern: adapters collect raw data,
deterministic code derives evidence, and LLM agents write only against those
bounded facts.

## Done

1. Market technical parsing.
   - Added a deterministic market summary parser for OHLCV, price range,
     return, volume ratio, volatility, drawdown, RSI, MACD, and 50/200 SMA.
   - The market analyst now calls one summary tool instead of parsing raw CSV
     and indicator strings itself.
   - Prefetch now warms the same stock-data window used by the summary tool.

## Next Surfaces

1. Fundamentals facts.
   - Emit normalized balance sheet, income statement, cash flow, leverage, and
     liquidity facts as structured records before the fundamentals analyst.
   - Add sector/accounting context flags such as `bank`, `insurer`, `reit`,
     and `capital-intensive industrial` so cash-flow and debt comments use the
     right interpretation.

2. News claim extraction.
   - Parse retrieved articles into dated source records with title, publisher,
     URL, published date, and a capped summary.
   - Require macro/company claims in news and social reports to cite one of
     those records.

3. Report proof checks.
   - Compare generated market report numbers against the deterministic market
     payload and flag out-of-payload prices, RSI, SMA, MACD, returns, and
     volume figures.
   - Extend the existing report quality checker from presence checks to numeric
     consistency checks.

4. Debate grounding.
   - Feed bull, bear, and risk agents compact fact packs rather than full
     analyst prose only.
   - Reject or annotate debate claims that introduce uncited AUM, price-target,
     or macro numbers.

5. Durable run artifacts.
   - Save normalized fact packs beside each report, e.g.
     `market_facts.json`, `fundamental_facts.json`, `news_sources.json`, and
     `claim_checks.json`.
   - This makes post-run review deterministic and avoids re-parsing generated
     prose.

6. Prepared-data analyst mode.
   - Build fact packs before analyst prompts and run selected analysts without
     tool loops where possible.
   - This improves quality and should also reduce local Ollama wall time.
