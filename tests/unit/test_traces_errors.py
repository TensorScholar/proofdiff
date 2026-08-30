from __future__ import annotations

from pathlib import Path

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.engine.traces import load_traces, parse_trace


def test_trace_validation_errors() -> None:
    with pytest.raises(InputError, match="case_id"):
        parse_trace({}, "memory")
    with pytest.raises(InputError, match="events"):
        parse_trace({"case_id": "x", "events": {}}, "memory")
    with pytest.raises(InputError, match="event must be an object"):
        parse_trace({"case_id": "x", "events": ["x"]}, "memory")
    with pytest.raises(InputError, match="event type"):
        parse_trace({"case_id": "x", "events": [{}]}, "memory")
    with pytest.raises(InputError, match="event name"):
        parse_trace({"case_id": "x", "events": [{"type": "x", "name": 1}]}, "memory")
    with pytest.raises(InputError, match="event content"):
        parse_trace({"case_id": "x", "events": [{"type": "x", "content": 1}]}, "memory")
    with pytest.raises(InputError, match="arguments and metadata"):
        parse_trace({"case_id": "x", "events": [{"type": "x", "arguments": []}]}, "memory")
    with pytest.raises(InputError, match="output"):
        parse_trace({"case_id": "x", "events": [], "output": 1}, "memory")
    with pytest.raises(InputError, match="trace metadata"):
        parse_trace({"case_id": "x", "events": [], "metadata": []}, "memory")
    with pytest.raises(InputError, match="must be an object"):
        parse_trace({"case_id": "x", "events": [], "metrics": []}, "memory")
    with pytest.raises(InputError, match="map strings to numbers"):
        parse_trace({"case_id": "x", "events": [], "metrics": {"cost": "x"}}, "memory")


def test_duplicate_trace_rejected(tmp_path: Path) -> None:
    path = tmp_path / "traces.jsonl"
    path.write_text('{"case_id":"x","events":[]}\n{"case_id":"x","events":[]}\n', encoding="utf-8")
    with pytest.raises(InputError, match="duplicate trace"):
        load_traces(path)
