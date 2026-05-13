from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.artifact_payloads import extract_artifact_from_messages
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_fundamentals_summary,
    get_language_instruction,
)


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
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals_summary,
        ]

        system_message = (
            "You are a researcher tasked with analyzing company fundamentals. Call get_fundamentals_summary exactly once for the instrument and current date before writing your report. The tool returns deterministic, parsed SEC facts plus accounting-context guardrails. Use those numeric values exactly and do not cite balance-sheet, income-statement, cash-flow, leverage, or liquidity figures that are absent from the tool result."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " For SEC-derived values, cite the period end, filing date, form type, accession, and source concept when the tool output provides them."
            + " Preserve the tool's accounting context. For banks and financial companies, do not treat negative operating cash flow as standalone distress, do not benchmark debt-to-equity or current-ratio style metrics like industrial companies, and do not claim liabilities exceed assets when the deterministic summary says assets exceed liabilities."
            + " Keep market valuation fields separate; do not invent market cap, AUM, price targets, dividend yields, or macro numbers unless another tool supplied them."
            + " Your role is analysis only; do not make the final BUY/HOLD/SELL portfolio decision, and do not include a recommendation to buy, hold, add, reduce, or sell."
            + get_language_instruction(),
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""
        fundamental_facts = state.get("fundamental_facts", {})

        if len(result.tool_calls) == 0:
            report = _strip_portfolio_recommendations(result.content)
            fundamental_facts = extract_artifact_from_messages(
                state.get("messages", []),
                "fundamental_facts",
            ) or fundamental_facts

        return {
            "messages": [result],
            "fundamentals_report": report,
            "fundamental_facts": fundamental_facts,
        }

    return fundamentals_analyst_node
