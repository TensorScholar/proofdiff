from __future__ import annotations

from copy import deepcopy

from proofdiff.domain.models import ChangeType, Severity
from proofdiff.engine.diff import compare_manifests


def _manifest(schema: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "agent": {"name": "support-agent", "revision": "1"},
        "runtime": {"provider": "fixture", "model": "m1", "temperature": 0},
        "instructions": "Use tools conservatively.",
        "tools": [
            {
                "name": "refund",
                "description": "Create a refund after approval.",
                "risk": "critical",
                "destructive": True,
                "input_schema": schema
                or {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "amount": {"type": "number", "minimum": 0, "maximum": 100},
                        "reason": {"type": "string", "minLength": 2, "maxLength": 100},
                    },
                    "required": ["amount"],
                },
                "timeout_seconds": 5,
            }
        ],
        "policy": {"allowed_tools": ["refund"]},
        "mcp": {"servers": []},
        "retrieval": {"corpus_digest": "a"},
        "source": {"commit": "a"},
        "environment": {"region": "test"},
    }


def _schema_change(before_schema: dict[str, object], after_schema: dict[str, object]):
    before = _manifest(before_schema)
    after = _manifest(after_schema)
    return next(
        item
        for item in compare_manifests(before, after).changes
        if item.path == "tools.refund.input_schema"
    )


def test_agent_policy_safety_and_extra_configuration_changes_are_conservative() -> None:
    before = _manifest()
    after = deepcopy(before)
    after["agent"] = {"name": "support-agent", "revision": "2"}
    tool = after["tools"][0]  # type: ignore[index]
    tool["risk"] = "low"  # type: ignore[index]
    tool["destructive"] = False  # type: ignore[index]
    tool["timeout_seconds"] = 30  # type: ignore[index]
    after["policy"] = {"allowed_tools": ["refund", "delete_account"]}

    changes = compare_manifests(before, after).changes
    by_type = {item.type: item for item in changes}
    assert by_type[ChangeType.AGENT_CONFIG_CHANGED].severity is Severity.HIGH
    assert by_type[ChangeType.TOOL_SAFETY_METADATA_CHANGED].severity is Severity.CRITICAL
    assert by_type[ChangeType.TOOL_SAFETY_METADATA_CHANGED].metadata["metadata_weakened"] is True
    assert by_type[ChangeType.TOOL_CONFIGURATION_CHANGED].metadata["changed_fields"] == [
        "timeout_seconds"
    ]
    assert by_type[ChangeType.POLICY_SCOPE_EXPANDED].severity is Severity.CRITICAL


def test_safety_metadata_tightening_is_high_not_critical() -> None:
    before = _manifest()
    before["tools"][0]["risk"] = "low"  # type: ignore[index]
    before["tools"][0]["destructive"] = False  # type: ignore[index]
    after = deepcopy(before)
    after["tools"][0]["risk"] = "high"  # type: ignore[index]
    change = next(
        item
        for item in compare_manifests(before, after).changes
        if item.type is ChangeType.TOOL_SAFETY_METADATA_CHANGED
    )
    assert change.severity is Severity.HIGH
    assert change.metadata["metadata_weakened"] is False


def test_schema_type_enum_and_additional_properties_directions() -> None:
    before = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"mode": {"type": "string", "enum": ["safe"]}},
        "required": ["mode"],
    }
    expanded = {
        "type": ["object", "null"],
        "additionalProperties": True,
        "properties": {"mode": {"type": "string", "enum": ["safe", "fast"]}},
        "required": [],
    }
    change = _schema_change(before, expanded)
    assert change.type is ChangeType.TOOL_INPUT_SCHEMA_EXPANDED
    reasons = change.metadata["reasons"]
    assert any("type widened" in reason for reason in reasons)
    assert any("enum added" in reason for reason in reasons)
    assert any("additionalProperties enabled" in reason for reason in reasons)

    restricted = _schema_change(expanded, before)
    assert restricted.type is ChangeType.TOOL_INPUT_SCHEMA_RESTRICTED
    assert any("type narrowed" in reason for reason in restricted.metadata["reasons"])


def test_schema_bounds_patterns_items_and_unknown_keywords_are_classified() -> None:
    before = {
        "type": "array",
        "minItems": 1,
        "maxItems": 10,
        "items": {"type": "string", "minLength": 1, "pattern": "^a"},
    }
    after = {
        "type": "array",
        "minItems": 0,
        "maxItems": 20,
        "items": {"type": "string", "minLength": 0},
    }
    expanded = _schema_change(before, after)
    assert expanded.type is ChangeType.TOOL_INPUT_SCHEMA_EXPANDED
    assert any("minItems lowered" in reason for reason in expanded.metadata["reasons"])
    assert any("maxItems raised" in reason for reason in expanded.metadata["reasons"])
    assert any("pattern constraint removed" in reason for reason in expanded.metadata["reasons"])

    mixed_before = {"type": "string", "const": "a", "x-custom": 1}
    mixed_after = {"type": "string", "const": "b", "x-custom": 2}
    mixed = _schema_change(mixed_before, mixed_after)
    assert mixed.type is ChangeType.TOOL_SCHEMA_CHANGED
    assert any("unclassified schema keywords changed" in reason for reason in mixed.metadata["reasons"])
    assert any("const changed" in reason for reason in mixed.metadata["reasons"])


def test_schema_property_and_items_shape_changes_are_mixed() -> None:
    before = {"type": "object", "properties": {"x": True}, "items": False}
    after = {"type": "object", "properties": {"x": {"type": "string"}}, "items": {"type": "string"}}
    change = _schema_change(before, after)
    assert change.type is ChangeType.TOOL_SCHEMA_CHANGED
    assert any("properties.x changed" in reason for reason in change.metadata["reasons"])
    assert any("items schema changed" in reason for reason in change.metadata["reasons"])


def test_schema_depth_limit_falls_back_to_bidirectional_review() -> None:
    before: dict[str, object] = {"type": "object"}
    after: dict[str, object] = {"type": "object"}
    left = before
    right = after
    for index in range(19):
        left["properties"] = {"x": {"type": "object"}}
        right["properties"] = {"x": {"type": "object"}}
        left = left["properties"]["x"]  # type: ignore[index,assignment]
        right = right["properties"]["x"]  # type: ignore[index,assignment]
    right["maxProperties"] = 1
    change = _schema_change(before, after)
    assert change.type is ChangeType.TOOL_SCHEMA_CHANGED
    assert any("depth exceeded" in reason for reason in change.metadata["reasons"])


def test_manifest_surfaces_and_unclassified_changes_are_detected() -> None:
    before = _manifest()
    after = deepcopy(before)
    after["mcp"] = {"servers": ["filesystem"]}
    after["retrieval"] = {"corpus_digest": "b"}
    after["source"] = {"commit": "b"}
    after["environment"] = {"region": "prod"}
    after["custom_surface"] = {"enabled": True}
    after["runtime"] = {"provider": "fixture2", "model": "m2", "temperature": 1}

    types = {item.type for item in compare_manifests(before, after).changes}
    assert {
        ChangeType.MCP_SERVER_CHANGED,
        ChangeType.RETRIEVAL_CORPUS_CHANGED,
        ChangeType.SOURCE_CODE_CHANGED,
        ChangeType.RUNTIME_CONFIG_CHANGED,
        ChangeType.UNCLASSIFIED_CHANGE,
        ChangeType.PROVIDER_CHANGED,
        ChangeType.MODEL_CHANGED,
    } <= types
