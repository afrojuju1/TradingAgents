# TradingAgents/graph/setup.py

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Any, Callable, Dict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState

from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)


_REPORT_FIELD_BY_ANALYST = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}


def _merge_node_update(state: dict, update: dict) -> None:
    """Apply a LangGraph-style node update to a local analyst state."""
    for key, value in update.items():
        if key == "messages":
            state.setdefault("messages", []).extend(value)
        else:
            state[key] = value


def _run_single_analyst_loop(
    *,
    analyst_type: str,
    analyst_node: Callable[[dict], dict],
    tool_node: ToolNode,
    base_state: dict,
    max_tool_iterations: int = 12,
) -> dict:
    """Run one analyst and its tool loop against an isolated message state."""
    start = perf_counter()
    report_field = _REPORT_FIELD_BY_ANALYST[analyst_type]
    state = {
        "messages": [HumanMessage(content=base_state["company_of_interest"])],
        "company_of_interest": base_state["company_of_interest"],
        "trade_date": base_state["trade_date"],
        "past_context": base_state.get("past_context", ""),
        "investment_debate_state": base_state["investment_debate_state"],
        "risk_debate_state": base_state["risk_debate_state"],
        "market_report": "",
        "sentiment_report": "",
        "news_report": "",
        "fundamentals_report": "",
        "market_facts": {},
        "fundamental_facts": {},
        "news_sources": {},
        "sentiment_facts": {},
        "claim_checks": [],
        "data_tool_events": [],
    }

    for _ in range(max_tool_iterations):
        analyst_update = analyst_node(state)
        _merge_node_update(state, analyst_update)

        last_message = state["messages"][-1]
        if not getattr(last_message, "tool_calls", None):
            logger.info(
                "Analyst completed: %s elapsed=%.2fs",
                analyst_type,
                perf_counter() - start,
            )
            result = {report_field: state.get(report_field, "")}
            for artifact_key in (
                "market_facts",
                "fundamental_facts",
                "news_sources",
                "sentiment_facts",
            ):
                if state.get(artifact_key):
                    result[artifact_key] = state[artifact_key]
            return result

        tool_names = [
            call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            for call in getattr(last_message, "tool_calls", [])
        ]
        logger.info(
            "Analyst tool call: %s iteration=%d tools=%s",
            analyst_type,
            len([message for message in state["messages"] if getattr(message, "tool_calls", None)]),
            ",".join(name for name in tool_names if name) or "unknown",
        )
        tool_update = tool_node.invoke(state)
        _merge_node_update(state, tool_update)

    raise RuntimeError(
        f"{analyst_type} analyst exceeded {max_tool_iterations} tool iterations"
    )


def _timed_node(name: str, node: Callable[[dict], dict]) -> Callable[[dict], dict]:
    def wrapped(state: dict) -> dict:
        start = perf_counter()
        logger.info("Node start: %s", name)
        try:
            return node(state)
        finally:
            logger.info("Node end: %s elapsed=%.2fs", name, perf_counter() - start)

    return wrapped


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
        parallel_analysts: bool = False,
        parallel_analyst_workers: int = 4,
        analyst_max_tool_iterations: int = 12,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic
        self.parallel_analysts = parallel_analysts
        self.parallel_analyst_workers = parallel_analyst_workers
        self.analyst_max_tool_iterations = max(1, int(analyst_max_tool_iterations))

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = _timed_node(
                "Market Analyst",
                create_market_analyst(self.quick_thinking_llm),
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            # "social" selector key preserved for back-compat with existing
            # user configs; the underlying agent has been renamed to
            # sentiment_analyst (the old name advertised social-media data
            # the agent never had access to — see issue #557).
            analyst_nodes["social"] = _timed_node(
                "Sentiment Analyst",
                create_sentiment_analyst(self.quick_thinking_llm),
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = _timed_node(
                "News Analyst",
                create_news_analyst(self.quick_thinking_llm),
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = _timed_node(
                "Fundamentals Analyst",
                create_fundamentals_analyst(self.quick_thinking_llm),
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # Create researcher and manager nodes
        bull_researcher_node = _timed_node(
            "Bull Researcher",
            create_bull_researcher(self.quick_thinking_llm),
        )
        bear_researcher_node = _timed_node(
            "Bear Researcher",
            create_bear_researcher(self.quick_thinking_llm),
        )
        research_manager_node = _timed_node(
            "Research Manager",
            create_research_manager(self.deep_thinking_llm),
        )
        trader_node = _timed_node("Trader", create_trader(self.quick_thinking_llm))

        # Create risk analysis nodes
        aggressive_analyst = _timed_node(
            "Aggressive Analyst",
            create_aggressive_debator(self.quick_thinking_llm),
        )
        neutral_analyst = _timed_node(
            "Neutral Analyst",
            create_neutral_debator(self.quick_thinking_llm),
        )
        conservative_analyst = _timed_node(
            "Conservative Analyst",
            create_conservative_debator(self.quick_thinking_llm),
        )
        portfolio_manager_node = _timed_node(
            "Portfolio Manager",
            create_portfolio_manager(self.deep_thinking_llm),
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        if self.parallel_analysts:
            workflow.add_node(
                "Parallel Analysts",
                self._create_parallel_analysts_node(
                    selected_analysts,
                    analyst_nodes,
                    tool_nodes,
                ),
            )
            workflow.add_edge(START, "Parallel Analysts")
            workflow.add_edge("Parallel Analysts", "Bull Researcher")
            workflow.add_conditional_edges(
                "Bull Researcher",
                self.conditional_logic.should_continue_debate,
                {
                    "Bear Researcher": "Bear Researcher",
                    "Research Manager": "Research Manager",
                },
            )
            workflow.add_conditional_edges(
                "Bear Researcher",
                self.conditional_logic.should_continue_debate,
                {
                    "Bull Researcher": "Bull Researcher",
                    "Research Manager": "Research Manager",
                },
            )
            workflow.add_edge("Research Manager", "Trader")
            workflow.add_edge("Trader", "Aggressive Analyst")
            workflow.add_conditional_edges(
                "Aggressive Analyst",
                self.conditional_logic.should_continue_risk_analysis,
                {
                    "Conservative Analyst": "Conservative Analyst",
                    "Portfolio Manager": "Portfolio Manager",
                },
            )
            workflow.add_conditional_edges(
                "Conservative Analyst",
                self.conditional_logic.should_continue_risk_analysis,
                {
                    "Neutral Analyst": "Neutral Analyst",
                    "Portfolio Manager": "Portfolio Manager",
                },
            )
            workflow.add_conditional_edges(
                "Neutral Analyst",
                self.conditional_logic.should_continue_risk_analysis,
                {
                    "Aggressive Analyst": "Aggressive Analyst",
                    "Portfolio Manager": "Portfolio Manager",
                },
            )
            workflow.add_edge("Portfolio Manager", END)
            return workflow

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow

    def _create_parallel_analysts_node(
        self,
        selected_analysts: list[str],
        analyst_nodes: Dict[str, Callable[[dict], dict]],
        tool_nodes: Dict[str, ToolNode],
    ) -> Callable[[dict], dict]:
        max_workers = max(1, min(self.parallel_analyst_workers, len(selected_analysts)))

        def parallel_analysts_node(state) -> dict:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _run_single_analyst_loop,
                        analyst_type=analyst_type,
                        analyst_node=analyst_nodes[analyst_type],
                        tool_node=tool_nodes[analyst_type],
                        base_state=state,
                        max_tool_iterations=self.analyst_max_tool_iterations,
                    ): analyst_type
                    for analyst_type in selected_analysts
                }

                reports = {}
                for future in as_completed(futures):
                    analyst_type = futures[future]
                    try:
                        reports.update(future.result())
                    except Exception as exc:
                        raise RuntimeError(
                            f"parallel {analyst_type} analyst failed"
                        ) from exc
                return reports

        return parallel_analysts_node
