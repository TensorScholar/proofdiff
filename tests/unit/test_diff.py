from __future__ import annotations

from proofdiff.domain.models import ChangeType, Severity
from proofdiff.engine.diff import compare_manifests


def manifest(tool_schema: dict[str, object], *, instructions: str = "safe") -> dict[str, object]:
    return {
        "agent": {"name": "a"},
        "runtime": {"provider": "fixture", "model": "m"},
        "instructions": instructions,
        "tools": [
            {
                "name": "refund",
                "description": "refund after approval",
                "risk": "critical",
                "input_schema": tool_schema,
            }
        ],
    }


def test_detects_schema_expansion() -> None:
    before = manifest(
        {
            "type": "object",
            "properties": {"confirmed": {"type": "boolean"}},
            "required": ["confirmed"],
        }
    )
    after = manifest(
        {
            "type": "object",
            "properties": {
                "confirmed": {"type": "boolean"},
                "amount": {"type": "number"},
            },
            "required": [],
        }
    )
    changes = compare_manifests(before, after).changes
    schema = next(item for item in changes if item.path == "tools.refund.input_schema")
    assert schema.type is ChangeType.TOOL_INPUT_SCHEMA_EXPANDED
    assert schema.severity is Severity.HIGH
    assert "new optional input property: amount" in schema.metadata["reasons"]
    assert "input property no longer required: confirmed" in schema.metadata["reasons"]


def test_detects_instruction_change() -> None:
    schema = {"type": "object", "properties": {}}
    changes = compare_manifests(manifest(schema), manifest(schema, instructions="fast")).changes
    assert any(item.type is ChangeType.SYSTEM_INSTRUCTION_CHANGED for item in changes)


def test_added_destructive_tool_is_critical() -> None:
    baseline = {"agent": {"name": "a"}, "runtime": {}, "tools": []}
    candidate = {
        "agent": {"name": "a"},
        "runtime": {},
        "tools": [
            {"name": "delete", "destructive": True, "input_schema": {"type": "object"}}
        ],
    }
    changes = compare_manifests(baseline, candidate).changes
    assert changes[0].type is ChangeType.TOOL_ADDED
    assert changes[0].severity is Severity.CRITICAL
