"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema,
   include_raw=True)`` where supported. Raw recovery lets us inspect the
   provider's tool-call payload when LangChain's parser rejects a small
   provider-specific shape variation.
2. At invocation, run the structured call, normalize the provider payload,
   validate it through the same Pydantic schema, and render the typed
   result back to markdown. If validation still fails (malformed JSON from
   a weak model, transient provider issue), fall back to a plain
   ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from enum import Enum
from types import UnionType
from typing import Any, Callable, Optional, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(ValueError):
    """Raised when a structured-output response cannot be validated."""


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return a structured-output binding or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        return llm.with_structured_output(schema, include_raw=True)
    except TypeError as exc:
        if "include_raw" not in str(exc):
            raise
        logger.debug(
            "%s: provider does not support include_raw for structured output; "
            "binding schema without raw recovery",
            agent_name,
        )
        try:
            return llm.with_structured_output(schema)
        except (NotImplementedError, AttributeError) as fallback_exc:
            logger.warning(
                "%s: provider does not support with_structured_output (%s); "
                "falling back to free-text generation",
                agent_name, fallback_exc,
            )
            return None
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None


def _parse_json_object(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return None

    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    for start in (0, text.find("{")):
        if start < 0:
            continue
        try:
            obj, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, Mapping):
            return dict(obj)
    return None


def _tool_call_payload(tool_call: Any) -> Any:
    if not isinstance(tool_call, Mapping):
        return None

    if "args" in tool_call:
        args = tool_call["args"]
        parsed = _parse_json_object(args)
        return parsed if parsed is not None else args

    function = tool_call.get("function")
    if isinstance(function, Mapping) and "arguments" in function:
        return _parse_json_object(function["arguments"])

    return None


def _raw_message_payload(raw: Any) -> Any:
    if raw is None:
        return None

    tool_calls = getattr(raw, "tool_calls", None)
    if tool_calls:
        for tool_call in tool_calls:
            payload = _tool_call_payload(tool_call)
            if payload is not None:
                return payload

    additional_kwargs = getattr(raw, "additional_kwargs", None)
    if isinstance(additional_kwargs, Mapping):
        for tool_call in additional_kwargs.get("tool_calls", []) or []:
            payload = _tool_call_payload(tool_call)
            if payload is not None:
                return payload

    content = getattr(raw, "content", raw)
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        for block in content:
            if isinstance(block, Mapping):
                for key in ("text", "content", "input"):
                    payload = _parse_json_object(block.get(key))
                    if payload is not None:
                        return payload
            else:
                payload = _parse_json_object(block)
                if payload is not None:
                    return payload
        return None

    return _parse_json_object(content)


def _single_wrapped_payload(schema: type[BaseModel], payload: dict[str, Any]) -> Any:
    if set(payload) & set(schema.model_fields):
        return payload
    if len(payload) != 1:
        return payload

    key, value = next(iter(payload.items()))
    schema_keys = {
        schema.__name__,
        schema.__name__.lower(),
        "".join(
            f"_{char.lower()}" if char.isupper() else char
            for char in schema.__name__
        ).lstrip("_"),
    }
    if key in schema_keys and isinstance(value, Mapping):
        return dict(value)
    return payload


def _unwrap_scalar(value: Any, preferred_keys: tuple[str, ...] = ()) -> Any:
    if not isinstance(value, Mapping):
        return value

    for key in (*preferred_keys, "value", "type", "label", "name", "text"):
        nested = value.get(key)
        if nested is not None and not isinstance(nested, (Mapping, list, tuple)):
            return nested
    return value


def _enum_type(annotation: Any) -> type[Enum] | None:
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation

    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        for arg in get_args(annotation):
            enum_type = _enum_type(arg)
            if enum_type is not None:
                return enum_type
    return None


def _coerce_enum(value: Any, enum_type: type[Enum], field_name: str) -> Any:
    value = _unwrap_scalar(value, (field_name,))
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        return value

    normalized = value.strip().strip("*")
    folded = normalized.casefold()
    for member in enum_type:
        if folded in {member.name.casefold(), str(member.value).casefold()}:
            return member.value
    return value


def _coerce_number(value: Any, annotation: Any) -> Any:
    value = _unwrap_scalar(value)
    origin = get_origin(annotation)
    args = get_args(annotation)
    numeric_type = None
    if annotation in (float, int):
        numeric_type = annotation
    elif origin in (Union, UnionType):
        if float in args:
            numeric_type = float
        elif int in args:
            numeric_type = int

    if numeric_type is None or not isinstance(value, str):
        return value

    stripped = value.strip().removeprefix("$").replace(",", "")
    if stripped.endswith("%"):
        stripped = stripped[:-1]
    try:
        return numeric_type(stripped)
    except ValueError:
        return value


def _normalize_payload(schema: type[T], payload: Any) -> Any:
    if isinstance(payload, schema):
        return payload
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    if not isinstance(payload, Mapping):
        return payload

    normalized = _single_wrapped_payload(schema, dict(payload))
    if not isinstance(normalized, Mapping):
        return normalized

    normalized = dict(normalized)
    for field_name, field_info in schema.model_fields.items():
        source_key = field_name
        if source_key not in normalized and field_info.alias in normalized:
            source_key = field_info.alias
        if source_key not in normalized:
            continue

        value = normalized.pop(source_key)
        enum_type = _enum_type(field_info.annotation)
        if enum_type is not None:
            value = _coerce_enum(value, enum_type, field_name)
        else:
            value = _coerce_number(value, field_info.annotation)
        normalized[field_name] = value
    return normalized


def _validate_structured_result(result: Any, schema: type[T]) -> T:
    payload = result
    parsing_error = None

    if isinstance(result, Mapping) and {"raw", "parsed", "parsing_error"} & set(result):
        parsed = result.get("parsed")
        parsing_error = result.get("parsing_error")
        if parsed is not None:
            payload = parsed
        else:
            payload = _raw_message_payload(result.get("raw"))
            if payload is None:
                raise StructuredOutputError(
                    f"structured parser returned no parsed value ({parsing_error})"
                )

    payload = _normalize_payload(schema, payload)
    if isinstance(payload, schema):
        return payload

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        if parsing_error is not None:
            raise StructuredOutputError(
                f"{exc}; raw structured parsing error was: {parsing_error}"
            ) from exc
        raise


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    schema: type[T],
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            return render(_validate_structured_result(result, schema))
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
