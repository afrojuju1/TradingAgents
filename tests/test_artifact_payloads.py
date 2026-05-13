from __future__ import annotations

from tradingagents.agents.utils.artifact_payloads import (
    append_artifact,
    extract_artifact,
    extract_artifact_from_messages,
    strip_artifacts,
)


class _Message:
    def __init__(self, content: str):
        self.content = content


def test_artifact_round_trip_from_text_and_messages():
    payload = {"ticker": "JPM", "value": 304.88}
    text = append_artifact("summary", "market_facts", payload)

    assert extract_artifact(text, "market_facts") == payload
    assert extract_artifact_from_messages([_Message(text)], "market_facts") == payload
    assert strip_artifacts(text) == "summary"
