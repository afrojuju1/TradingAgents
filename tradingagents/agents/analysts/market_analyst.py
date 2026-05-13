from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.artifact_payloads import extract_artifact_from_messages
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_market_summary,
)


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_market_summary,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets.
Call get_market_summary exactly once for the instrument and current date before writing your report.
The tool returns deterministic, parsed market facts for price action, volume, volatility, RSI, MACD, and 50/200-day moving averages.
Use those numeric values exactly when citing technical evidence. Do not quote a price, range, SMA, RSI, MACD, volume, return, or volatility value that is absent from the tool result.
Write a concise but nuanced market report that separates trend, momentum, volatility, support/resistance, and technical risk."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + " Your role is analysis only; do not make the final BUY/HOLD/SELL portfolio decision."
            + get_language_instruction()
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
        market_facts = state.get("market_facts", {})

        if len(result.tool_calls) == 0:
            report = result.content
            market_facts = extract_artifact_from_messages(
                state.get("messages", []),
                "market_facts",
            ) or market_facts

        return {
            "messages": [result],
            "market_report": report,
            "market_facts": market_facts,
        }

    return market_analyst_node
