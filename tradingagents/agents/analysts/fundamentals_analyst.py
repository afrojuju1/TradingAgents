from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.artifact_payloads import extract_artifact, strip_artifacts
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_event_calendar_summary,
    get_fundamentals_summary,
    get_language_instruction,
    get_valuation_summary,
)
from tradingagents.agents.utils.report_budget import get_report_budget_instruction


def _strip_portfolio_recommendations(report: str) -> str:
    """Remove portfolio-action recommendation blocks from analyst output."""
    lines = report.splitlines()
    cleaned: list[str] = []
    skipping = False

    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        is_recommendation_start = (
            "recommendation" in lowered
            and (
                lowered.startswith(("recommendation", "**recommendation", "#"))
                or lowered.rstrip(":").endswith("recommendation")
                or "**recommendation" in lowered
            )
        )

        if is_recommendation_start:
            skipping = True
            continue

        if skipping:
            if not stripped:
                skipping = False
            elif stripped == "---":
                skipping = False
                cleaned.append(line)
            elif stripped.startswith("#") and "recommendation" not in lowered:
                skipping = False
                cleaned.append(line)
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        tool_output = get_fundamentals_summary.func(ticker, current_date)
        fundamentals_summary = strip_artifacts(tool_output)
        fundamental_facts = extract_artifact(
            tool_output,
            "fundamental_facts",
        ) or state.get("fundamental_facts", {})
        valuation_output = get_valuation_summary.func(ticker, current_date)
        valuation_summary = strip_artifacts(valuation_output)
        valuation_facts = extract_artifact(
            valuation_output,
            "valuation_facts",
        ) or state.get("valuation_facts", {})
        event_output = get_event_calendar_summary.func(ticker, current_date)
        event_summary = strip_artifacts(event_output)
        event_facts = extract_artifact(event_output, "event_facts") or state.get(
            "event_facts",
            {},
        )

        system_message = (
            "You are a researcher tasked with analyzing company fundamentals. You have already been given deterministic, parsed SEC facts plus accounting-context guardrails. Use those numeric values exactly and do not cite balance-sheet, income-statement, cash-flow, leverage, or liquidity figures that are absent from the summary."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " For SEC-derived values, cite the period end, filing date, form type, accession, and source concept when the summary provides them."
            + " Preserve the summary's accounting context. For banks and financial companies, do not treat negative operating cash flow as standalone distress, do not benchmark debt-to-equity or current-ratio style metrics like industrial companies, and do not claim liabilities exceed assets when the deterministic summary says assets exceed liabilities."
            + " Keep valuation and event fields separate; cite market cap, enterprise value, P/E, dividend yield, and calendar dates only when the valuation or event summaries provide them. Do not invent AUM, price targets, peer medians, buyback yield, or macro numbers."
            + " Your role is analysis only; do not make the final BUY/HOLD/SELL portfolio decision, and do not include a recommendation to buy, hold, add, reduce, or sell."
            + get_report_budget_instruction("analyst")
            + f"\n\nDeterministic fundamentals summary:\n{fundamentals_summary}"
            + f"\n\nDeterministic valuation summary:\n{valuation_summary}"
            + f"\n\nDeterministic event calendar summary:\n{event_summary}"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm

        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "fundamentals_report": _strip_portfolio_recommendations(result.content),
            "fundamental_facts": fundamental_facts,
            "valuation_facts": valuation_facts,
            "event_facts": event_facts,
        }

    return fundamentals_analyst_node
