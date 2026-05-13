from __future__ import annotations

import json
import re
from typing import Any


_ARTIFACT_RE = re.compile(
    r"<!-- tradingagents-artifact:(?P<name>[a-zA-Z0-9_]+)\n"
    r"(?P<payload>.*?)\n-->",
    re.DOTALL,
)


def append_artifact(markdown: str, name: str, payload: dict[str, Any]) -> str:
    """Attach a compact machine-readable artifact to tool output."""
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return f"{markdown}\n\n<!-- tradingagents-artifact:{name}\n{serialized}\n-->"


def extract_artifact(text: str, name: str) -> dict[str, Any] | None:
    for match in _ARTIFACT_RE.finditer(text or ""):
        if match.group("name") != name:
            continue
        try:
            return json.loads(match.group("payload"))
        except json.JSONDecodeError:
            return None
    return None


def extract_artifact_from_messages(messages: list[Any], name: str) -> dict[str, Any] | None:
    for message in reversed(messages or []):
        content = getattr(message, "content", None)
        if isinstance(content, str):
            payload = extract_artifact(content, name)
            if payload is not None:
                return payload
    return None


def strip_artifacts(text: str) -> str:
    return _ARTIFACT_RE.sub("", text or "").strip()
