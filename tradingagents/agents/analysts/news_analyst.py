from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.artifact_payloads import extract_artifact_from_messages
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news_summary,
)


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news_summary,
        ]

        system_message = (
            "You are a news researcher tasked with analyzing recent company and macro news. Call get_news_summary exactly once for the instrument and current date before writing your report. The tool returns deterministic source records with source IDs, publishers, URLs, summaries, and relevance scores. Cite source IDs for every material news claim, and do not introduce CPI, Fed, oil, dividend, AUM, market-cap, or price-target numbers unless they appear in the tool result."
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
        news_sources = state.get("news_sources", {})

        if len(result.tool_calls) == 0:
            report = result.content
            news_sources = extract_artifact_from_messages(
                state.get("messages", []),
                "news_sources",
            ) or news_sources

        return {
            "messages": [result],
            "news_report": report,
            "news_sources": news_sources,
        }

    return news_analyst_node
