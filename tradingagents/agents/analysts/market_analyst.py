from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.artifact_payloads import extract_artifact, strip_artifacts
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_market_summary,
)


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        tool_output = get_market_summary.func(ticker, current_date)
        market_summary = strip_artifacts(tool_output)
        market_facts = extract_artifact(tool_output, "market_facts") or state.get(
            "market_facts",
            {},
        )

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets.
You have already been given a deterministic, parsed market summary for price action, volume, volatility, RSI, MACD, and 50/200-day moving averages.
Use those numeric values exactly when citing technical evidence. Do not quote a price, range, SMA, RSI, MACD, volume, return, or volatility value that is absent from the summary.
Write a concise but nuanced market report that separates trend, momentum, volatility, support/resistance, and technical risk."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + " Your role is analysis only; do not make the final BUY/HOLD/SELL portfolio decision."
            + f"\n\nDeterministic market summary:\n{market_summary}"
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
            "market_report": result.content,
            "market_facts": market_facts,
        }

    return market_analyst_node
