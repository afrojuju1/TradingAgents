"""Named run profiles for common local speed/quality tradeoffs."""

from __future__ import annotations

from copy import deepcopy


DEFAULT_ANALYSTS = ["market", "social", "news", "fundamentals"]

RUN_PROFILES = {
    "fast": {
        "description": "Small local Ollama run for quick iteration.",
        "selected_analysts": ["market", "fundamentals"],
        "config": {
            "llm_provider": "ollama",
            "quick_think_llm": "qwen3:8b",
            "deep_think_llm": "qwen3:8b",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "parallel_analysts": True,
            "parallel_analyst_workers": 2,
            "data_tool_cache_enabled": True,
        },
    },
    "balanced": {
        "description": "Default local Ollama profile for complete single-ticker runs.",
        "selected_analysts": DEFAULT_ANALYSTS,
        "config": {
            "llm_provider": "ollama",
            "quick_think_llm": "qwen3:8b",
            "deep_think_llm": "glm-4.7-flash:latest",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "parallel_analysts": True,
            "parallel_analyst_workers": 2,
            "data_tool_cache_enabled": True,
        },
    },
    "quality": {
        "description": "Higher-quality local Ollama run with a larger deep model.",
        "selected_analysts": DEFAULT_ANALYSTS,
        "config": {
            "llm_provider": "ollama",
            "quick_think_llm": "qwen3:8b",
            "deep_think_llm": "qwen3.6:35b",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "parallel_analysts": True,
            "parallel_analyst_workers": 2,
            "data_tool_cache_enabled": True,
        },
    },
}


def apply_run_profile(config: dict, profile_name: str | None) -> dict:
    """Apply a named profile to config in-place and return it."""
    profile_key = (profile_name or "").strip().lower()
    config["run_profile"] = profile_key or None
    if not profile_key:
        return config

    if profile_key not in RUN_PROFILES:
        valid = ", ".join(sorted(RUN_PROFILES))
        raise ValueError(
            f"Unknown TRADINGAGENTS_RUN_PROFILE '{profile_name}'. Choose from: {valid}."
        )

    profile = RUN_PROFILES[profile_key]
    config.update(deepcopy(profile["config"]))
    config["selected_analysts"] = list(profile["selected_analysts"])
    config["run_profile"] = profile_key
    return config
