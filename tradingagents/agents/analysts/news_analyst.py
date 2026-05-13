from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.artifact_payloads import extract_artifact, strip_artifacts
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news_summary,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)
        tool_output = get_news_summary.func(ticker, current_date)
        news_summary = strip_artifacts(tool_output)
        news_sources = extract_artifact(tool_output, "news_sources") or state.get(
            "news_sources",
            {},
        )

        system_message = (
            "You are a news researcher tasked with analyzing recent company and macro news. You have already been given deterministic source records with source IDs, publishers, URLs, summaries, and relevance scores. Cite source IDs for every material news claim, and do not introduce CPI, Fed, oil, dividend, AUM, market-cap, or price-target numbers unless they appear in the summary."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + " Your role is analysis only; do not make the final BUY/HOLD/SELL portfolio decision."
            + f"\n\nDeterministic news summary:\n{news_summary}"
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
            "news_report": result.content,
            "news_sources": news_sources,
        }

    return news_analyst_node
