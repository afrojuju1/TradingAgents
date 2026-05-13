"""Tests for optional parallel analyst execution."""

from __future__ import annotations

from threading import Barrier

from langgraph.prebuilt import ToolNode

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.setup import (
    GraphSetup,
    _run_single_analyst_loop,
)


class _Message:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _ToolNode:
    def __init__(self):
        self.calls = 0

    def invoke(self, state):
        self.calls += 1
        return {"messages": [_Message("tool result")]}


class _DummyLLM:
    def with_structured_output(self, schema):
        return self


def _base_state():
    return {
        "company_of_interest": "AMD",
        "trade_date": "2026-05-12",
        "past_context": "",
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
    }


def test_single_analyst_loop_runs_tool_then_report():
    calls = {"analyst": 0}
    tool_node = _ToolNode()

    def analyst_node(state):
        calls["analyst"] += 1
        if calls["analyst"] == 1:
            return {"messages": [_Message(tool_calls=[{"name": "fetch"}])]}
        assert state["messages"][-1].content == "tool result"
        return {
            "messages": [_Message("done")],
            "market_report": "market report",
        }

    result = _run_single_analyst_loop(
        analyst_type="market",
        analyst_node=analyst_node,
        tool_node=tool_node,
        base_state=_base_state(),
    )

    assert result == {"market_report": "market report"}
    assert calls["analyst"] == 2
    assert tool_node.calls == 1


def test_parallel_analysts_node_runs_independent_reports_concurrently():
    barrier = Barrier(2)

    def make_node(report_field, report):
        def node(state):
            barrier.wait(timeout=2)
            return {
                "messages": [_Message(report)],
                report_field: report,
            }

        return node

    setup = GraphSetup(
        quick_thinking_llm=object(),
        deep_thinking_llm=object(),
        tool_nodes={},
        conditional_logic=object(),
        parallel_analysts=True,
        parallel_analyst_workers=2,
    )
    node = setup._create_parallel_analysts_node(
        ["market", "news"],
        {
            "market": make_node("market_report", "market report"),
            "news": make_node("news_report", "news report"),
        },
        {
            "market": _ToolNode(),
            "news": _ToolNode(),
        },
    )

    result = node(_base_state())

    assert result == {
        "market_report": "market report",
        "news_report": "news report",
    }


def test_parallel_analysts_graph_compiles():
    setup = GraphSetup(
        quick_thinking_llm=_DummyLLM(),
        deep_thinking_llm=_DummyLLM(),
        tool_nodes={
            "market": ToolNode([]),
            "social": ToolNode([]),
            "news": ToolNode([]),
            "fundamentals": ToolNode([]),
        },
        conditional_logic=ConditionalLogic(),
        parallel_analysts=True,
        parallel_analyst_workers=2,
    )

    workflow = setup.setup_graph(["market", "news"])

    assert workflow.compile() is not None
