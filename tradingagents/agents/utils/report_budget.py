from __future__ import annotations

from tradingagents.dataflows.config import get_config


DEFAULT_REPORT_BUDGETS = {
    "analyst": {"max_words": 450, "max_sections": 5, "max_bullets": 4},
    "debate": {"max_words": 300, "max_sections": 3, "max_bullets": 4},
    "manager": {"max_words": 350, "max_sections": 4, "max_bullets": 4},
    "trader": {"max_words": 300, "max_sections": 4, "max_bullets": 4},
    "risk": {"max_words": 260, "max_sections": 3, "max_bullets": 4},
    "portfolio": {"max_words": 350, "max_sections": 4, "max_bullets": 4},
}


def get_report_budget_instruction(role: str) -> str:
    """Return concise output-budget guidance for agent prompts."""
    configured = get_config().get("report_budgets", {})
    budget = {
        **DEFAULT_REPORT_BUDGETS.get(role, DEFAULT_REPORT_BUDGETS["analyst"]),
        **configured.get(role, {}),
    }
    return (
        f" Keep the output under about {budget['max_words']} words, with no more "
        f"than {budget['max_sections']} short sections and {budget['max_bullets']} "
        "bullets per section. Prefer evidence-dense statements over repeated "
        "generic commentary."
    )
