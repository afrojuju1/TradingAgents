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

## Backlog

1. [Done] Parallelize independent analyst nodes.
   - Run market, sentiment, news, and fundamentals analysts concurrently.
   - Merge their reports before the researcher stage.
   - Implemented as an opt-in path behind `parallel_analysts` /
     `TRADINGAGENTS_PARALLEL_ANALYSTS` so hosted providers keep the
     conservative serial flow by default.

2. Prefetch data before LLM calls.
   - Fetch price, indicators, fundamentals, news, Reddit, and StockTwits once.
   - Pass prepared data to analyst prompts instead of letting each analyst
     discover data through tool-call loops.

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

8. Improve CLI observability for non-interactive runs.
   - Log node start/end timestamps.
   - Log model name, tool-call counts, and elapsed time per node.
   - Save partial progress in a readable run log.

9. Benchmark profiles.
   - Run the same ticker/date through fast, balanced, and quality profiles.
   - Record wall time, model reloads, VRAM use, and final rating.

10. Review checkpoint/resume after serialization fix.
    - Confirm checkpointing works through a full local Ollama graph run.
    - Keep checkpoint state small enough that saving does not dominate runtime.
