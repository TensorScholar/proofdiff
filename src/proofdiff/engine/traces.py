from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from proofdiff.domain.errors import InputError
from proofdiff.domain.models import TraceEvent, TraceRecord
from proofdiff.engine.canonical import normalize
from proofdiff.engine.io import load_jsonl

CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
MAX_TRACE_EVENTS = 10_000
MAX_OUTPUT_CHARS = 1_000_000
MAX_METRICS = 1_000


def _number_map(value: Any, field: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    if len(value) > MAX_METRICS:
        raise InputError(f"{field} exceeds {MAX_METRICS} entries")
    result: dict[str, float] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or key != key.strip()
            or not isinstance(item, (int, float))
            or isinstance(item, bool)
        ):
            raise InputError(f"{field} must map strings to numbers; keys must be trimmed and values finite")
        number = float(item)
        if not math.isfinite(number):
            raise InputError(f"{field} contains a non-finite value for {key}")
        result[key] = number
    return result


def parse_trace(value: dict[str, Any], source: str) -> TraceRecord:
    allowed = {"case_id", "events", "output", "metrics", "metadata"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise InputError(f"trace contains unknown fields at {source}: {', '.join(unknown)}")
    case_id = value.get("case_id")
    if not isinstance(case_id, str) or CASE_ID.fullmatch(case_id) is None:
        raise InputError(f"trace case_id must match {CASE_ID.pattern!r}: {source}")
    events_raw = value.get("events", [])
    if not isinstance(events_raw, list):
        raise InputError(f"trace events must be an array: {source}")
    if len(events_raw) > MAX_TRACE_EVENTS:
        raise InputError(f"trace exceeds {MAX_TRACE_EVENTS} events: {source}")

    events: list[TraceEvent] = []
    for index, raw in enumerate(events_raw):
        if not isinstance(raw, dict):
            raise InputError(f"trace event must be an object: {source} event {index}")
        allowed_event = {"type", "name", "content", "arguments", "metadata"}
        unknown_event = sorted(set(raw) - allowed_event)
        if unknown_event:
            raise InputError(
                f"trace event contains unknown fields: {source} event {index}: {', '.join(unknown_event)}"
            )
        event_type = raw.get("type")
        if (
            not isinstance(event_type, str)
            or not event_type
            or event_type != event_type.strip()
            or len(event_type) > 128
        ):
            raise InputError(f"trace event type must be a trimmed string up to 128 chars: {source} event {index}")
        name = raw.get("name")
        content = raw.get("content")
        arguments = raw.get("arguments", {})
        metadata = raw.get("metadata", {})
        if name is not None and (
            not isinstance(name, str)
            or not name
            or name != name.strip()
            or len(name) > 256
        ):
            raise InputError(f"trace event name must be a trimmed string up to 256 chars: {source} event {index}")
        if content is not None and not isinstance(content, str):
            raise InputError(f"trace event content must be a string: {source} event {index}")
        if content is not None and len(content) > MAX_OUTPUT_CHARS:
            raise InputError(f"trace event content is too large: {source} event {index}")
        if not isinstance(arguments, dict) or not isinstance(metadata, dict):
            raise InputError(f"trace event arguments and metadata must be objects: {source} event {index}")
        events.append(
            TraceEvent(
                event_type,
                name,
                content,
                normalize(arguments),
                normalize(metadata),
            )
        )

    output = value.get("output", "")
    if not isinstance(output, str):
        raise InputError(f"trace output must be a string: {source}")
    if len(output) > MAX_OUTPUT_CHARS:
        raise InputError(f"trace output exceeds {MAX_OUTPUT_CHARS} characters: {source}")
    metadata = value.get("metadata", {})
    if not isinstance(metadata, dict):
        raise InputError(f"trace metadata must be an object: {source}")
    return TraceRecord(
        case_id=case_id,
        events=tuple(events),
        output=output,
        metrics=_number_map(value.get("metrics"), f"{source}.metrics"),
        metadata=normalize(metadata),
    )


def load_traces(path: str | Path) -> dict[str, TraceRecord]:
    records = [parse_trace(value, f"{path}:{index + 1}") for index, value in enumerate(load_jsonl(path))]
    result: dict[str, TraceRecord] = {}
    for record in records:
        if record.case_id in result:
            raise InputError(f"duplicate trace case_id: {record.case_id}")
        result[record.case_id] = record
    return result
