# Ollama Performance Plan

This captures the follow-up ideas from the Ollama tuning review. The checkpoint
serialization fix is handled separately.

SEC fundamentals accuracy, edgartools integration, and Gluetun routing are
tracked in `docs/sec_fundamentals_plan.md`.

## Current Local Ollama Profile

- GPU backend: ROCm on Radeon AI PRO R9700
- `OLLAMA_CONTEXT_LENGTH=16384`
- `OLLAMA_NUM_PARALLEL=2`
- `OLLAMA_MAX_LOADED_MODELS=2`
- `OLLAMA_KEEP_ALIVE=2h`
- `OLLAMA_FLASH_ATTENTION=1`
- `OLLAMA_KV_CACHE_TYPE=q8_0`
- Quick model: `qwen3:8b`
- Balanced deep model: `glm-4.7-flash:latest`
- High quality deep model, slower: `qwen3.6:35b`

## Observed Constraints

- `qwen3:8b` supports two parallel Ollama requests on this setup.
- `qwen3.6:35b` and `qwen3.5:27b-q4_K_M` reported that their architecture
  does not currently support parallel requests.
- At 32K context, the larger deep models cause model eviction/reload churn.
- At 16K context, `qwen3:8b` and `glm-4.7-flash:latest` can stay resident
  together on GPU.
- The current TradingAgents graph is mostly sequential, so Ollama parallelism
  helps multi-ticker runs more than a single run until the graph is changed.
- The local `.env` opts into analyst parallelism with
  `TRADINGAGENTS_PARALLEL_ANALYSTS=true` and
  `TRADINGAGENTS_PARALLEL_ANALYST_WORKERS=2` to match the current Ollama
  `OLLAMA_NUM_PARALLEL=2` setting.
- The local `.env` can opt into vendor tool-result caching with
  `TRADINGAGENTS_DATA_TOOL_CACHE_ENABLED=true`.
- `TRADINGAGENTS_RUN_PROFILE=fast|balanced|quality` applies the local Ollama
  presets described below. Specific model env vars still override the profile.

## Measured Runs

### JPM Full E2E, Balanced Local Profile

- Ticker/date: `JPM` on `2026-05-12`
- Report: `reports/JPM_20260513_010305/complete_report.md`
- Metadata: `reports/JPM_20260513_010305/run_metadata.json`
- Decision: `Hold`
- Wall time: 479.5s
- LLM calls: 15
- Token usage: 82,543 input / 25,524 output
- Config: Ollama, quick `qwen3:8b`, deep `glm-4.7-flash:latest`,
  analyst parallelism enabled with 2 workers, prefetch/cache enabled.
- Quality check: `scripts/check_report_quality.py reports/JPM_20260513_010305 --require-sec`
  passed after metadata was written.
- GPU status: `ollama ps` reported both models resident at `100% GPU`.
  `nvidia-smi` is not installed in this environment.

Timing breakdown:

| Stage | Time |
| --- | ---: |
| Warm prefetch/cache | 0.0s |
| Parallel analyst block | 227.6s |
| Bull researcher | 47.4s |
| Bear researcher | 56.0s |
| Research manager | 24.4s |
| Trader | 7.0s |
| Risk debators total | 98.4s |
| Portfolio manager | 18.3s |

Analyst block details:

| Analyst | Time |
| --- | ---: |
| Market | 126.7s |
| Fundamentals | 101.0s |
| Sentiment | 71.6s |
| News | 67.1s |

Main finding: with warm cache, data fetching is not the bottleneck. Runtime is
almost entirely LLM generation and tool-loop turns. The largest single target is
market analysis, followed by fundamentals and the sequential risk debate.

## Backlog

1. [Done] Parallelize independent analyst nodes.
   - Run market, sentiment, news, and fundamentals analysts concurrently.
   - Merge their reports before the researcher stage.
   - Implemented as an opt-in path behind `parallel_analysts` /
     `TRADINGAGENTS_PARALLEL_ANALYSTS` so hosted providers keep the
     conservative serial flow by default.

2. [Partial] Prefetch data before LLM calls.
   - Fetch price, indicators, fundamentals, news, Reddit, and StockTwits once.
   - Current implementation warms the vendor tool cache before LLM calls.
   - Remaining work: pass prepared data directly to analyst prompts so analysts
     can skip data-discovery tool-call turns entirely.

3. [Done] Add ticker/date data caching.
   - Cache yfinance, financial statements, news, and social data under the
     configured cache directory.
   - Key by ticker, trade date, vendor, and lookback window.
   - Implemented as an opt-in vendor tool-result cache keyed by method,
     vendor, args, and kwargs, with per-key locking for concurrent analysts.

4. [Done] Add a fast run profile.
   - Quick and deep model both set to `qwen3:8b`.
   - Analysts reduced to market plus fundamentals by default.
   - Prompt/report trimming remains tracked separately below.
   - Implemented as `TRADINGAGENTS_RUN_PROFILE=fast`.

5. [Done] Add a balanced run profile.
   - Quick model `qwen3:8b`.
   - Deep model `glm-4.7-flash:latest`.
   - All analysts enabled, one debate round, one risk round.
   - Implemented as `TRADINGAGENTS_RUN_PROFILE=balanced`.

6. [Done] Add a quality run profile.
   - Quick model `qwen3:8b`.
   - Deep model `qwen3.6:35b`.
   - Accept model reload cost for final research and portfolio quality.
   - Implemented as `TRADINGAGENTS_RUN_PROFILE=quality`.

7. Trim prompt and report size.
   - Remove repeated generic instructions across agents.
   - Add explicit concise report targets.
   - Consider per-agent token limits.
   - JPM used 82,543 input tokens and 25,524 output tokens across 15 LLM calls;
     token volume is now the clearest speed target.

8. Improve CLI observability for non-interactive runs.
   - Log node start/end timestamps.
   - Log model name, tool-call counts, and elapsed time per node.
   - Save partial progress in a readable run log.
   - The ad-hoc JPM timing harness exposed useful timings; this should become
     a reusable non-interactive command so future runs do not depend on inline
     scripts.

9. Benchmark profiles.
   - Run the same ticker/date through fast, balanced, and quality profiles.
   - Record wall time, model reloads, VRAM use, and final rating.

10. Review checkpoint/resume after serialization fix.
    - Confirm checkpointing works through a full local Ollama graph run.
    - Keep checkpoint state small enough that saving does not dominate runtime.

11. Add a prepared-data analyst mode.
    - Build all selected data payloads before analyst prompts.
    - Feed compact, capped data summaries into the analyst prompt.
    - Disable tool binding for prepared analysts.
    - Expected savings from JPM: eliminate market/news/fundamentals
      data-discovery turns, roughly 60-70s before any prompt-size savings.

12. Parallelize first-round risk debators.
    - Aggressive, conservative, and neutral risk analysts currently run
      sequentially and took 98.4s combined on JPM.
    - Their first-round opinions can be generated from the same trader state,
      then merged for Portfolio Manager review.

13. Add report length budgets per agent.
    - Market and fundamentals are the slowest analyst reports.
    - Set concrete section and word-count targets instead of asking for very
      detailed reports everywhere.
