from __future__ import annotations

from proofdiff.domain.models import ChangeType
from proofdiff.engine.diff import compare_manifests


def base() -> dict[str, object]:
    return {
        "agent": {"name": "a"},
        "runtime": {"provider": "p1", "model": "m1", "temperature": 0},
        "instructions": "safe",
        "tools": [
            {
                "name": "x",
                "description": "old",
                "input_schema": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": [],
                },
            }
        ],
        "mcp": {"servers": []},
        "policy": {"digest": "a"},
        "retrieval": {"digest": "a"},
        "source": {"commit": "a"},
    }


def test_detects_multiple_surface_changes() -> None:
    before = base()
    after = base()
    after["runtime"] = {"provider": "p2", "model": "m2", "temperature": 1}
    after["mcp"] = {"servers": ["x"]}
    after["policy"] = {"digest": "b"}
    after["retrieval"] = {"digest": "b"}
    after["source"] = {"commit": "b"}
    after["custom"] = {"x": 1}
    types = {item.type for item in compare_manifests(before, after).changes}
    assert {
        ChangeType.PROVIDER_CHANGED,
        ChangeType.MODEL_CHANGED,
        ChangeType.RUNTIME_CONFIG_CHANGED,
        ChangeType.MCP_SERVER_CHANGED,
        ChangeType.POLICY_CHANGED,
        ChangeType.RETRIEVAL_CORPUS_CHANGED,
        ChangeType.SOURCE_CODE_CHANGED,
        ChangeType.UNCLASSIFIED_CHANGE,
    } <= types


def test_detects_tool_description_restriction_removal_and_generic_schema_change() -> None:
    before = base()
    after = base()
    after["tools"] = [
        {
            "name": "x",
            "description": "new",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
    ]
    types = [item.type for item in compare_manifests(before, after).changes]
    assert ChangeType.TOOL_DESCRIPTION_CHANGED in types
    assert ChangeType.TOOL_INPUT_SCHEMA_RESTRICTED in types

    generic_before = base()
    generic_after = base()
    generic_after["tools"] = [
        {
            "name": "x",
            "description": "old",
            "input_schema": {
                "type": "array",
                "items": {"type": "string"},
                "properties": {"q": {"type": "string"}},
                "required": [],
            },
        }
    ]
    assert ChangeType.TOOL_SCHEMA_CHANGED in {
        item.type for item in compare_manifests(generic_before, generic_after).changes
    }

    removed = base()
    removed["tools"] = []
    assert ChangeType.TOOL_REMOVED in {item.type for item in compare_manifests(before, removed).changes}
