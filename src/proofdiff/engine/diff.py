from __future__ import annotations

from typing import Any

from proofdiff.domain.models import Change, ChangeSet, ChangeType, Severity
from proofdiff.engine.canonical import digest

_SCHEMA_DEPTH_LIMIT = 16
_TOOL_KNOWN_FIELDS = {"name", "description", "input_schema", "risk", "destructive"}
_RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def _tool_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(tool["name"]): tool for tool in manifest.get("tools", [])}


def _type_set(schema: dict[str, Any]) -> set[str] | None:
    value = schema.get("type")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    return None


def _compare_lower_bound(
    before: dict[str, Any],
    after: dict[str, Any],
    key: str,
    path: str,
    expansions: list[str],
    restrictions: list[str],
) -> None:
    old = before.get(key)
    new = after.get(key)
    if old == new:
        return
    if old is None and isinstance(new, (int, float)):
        restrictions.append(f"{path}{key} added: {new}")
    elif new is None and isinstance(old, (int, float)):
        expansions.append(f"{path}{key} removed")
    elif isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if new < old:
            expansions.append(f"{path}{key} lowered from {old} to {new}")
        elif new > old:
            restrictions.append(f"{path}{key} raised from {old} to {new}")


def _compare_upper_bound(
    before: dict[str, Any],
    after: dict[str, Any],
    key: str,
    path: str,
    expansions: list[str],
    restrictions: list[str],
) -> None:
    old = before.get(key)
    new = after.get(key)
    if old == new:
        return
    if old is None and isinstance(new, (int, float)):
        restrictions.append(f"{path}{key} added: {new}")
    elif new is None and isinstance(old, (int, float)):
        expansions.append(f"{path}{key} removed")
    elif isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if new > old:
            expansions.append(f"{path}{key} raised from {old} to {new}")
        elif new < old:
            restrictions.append(f"{path}{key} lowered from {old} to {new}")


def _schema_directions(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    path: str = "",
    depth: int = 0,
) -> tuple[list[str], list[str]]:
    if depth > _SCHEMA_DEPTH_LIMIT:
        return [f"{path or '<root>'} schema depth exceeded semantic classifier"], [
            f"{path or '<root>'} schema depth exceeded semantic classifier"
        ]

    expansions: list[str] = []
    restrictions: list[str] = []
    prefix = f"{path}." if path else ""

    old_types = _type_set(before)
    new_types = _type_set(after)
    if old_types is not None and new_types is not None and old_types != new_types:
        added = sorted(new_types - old_types)
        removed = sorted(old_types - new_types)
        if added:
            expansions.append(f"{prefix}type widened with {', '.join(added)}")
        if removed:
            restrictions.append(f"{prefix}type narrowed by removing {', '.join(removed)}")
    elif old_types != new_types:
        expansions.append(f"{prefix}type declaration changed")
        restrictions.append(f"{prefix}type declaration changed")

    old_enum = before.get("enum")
    new_enum = after.get("enum")
    if isinstance(old_enum, list) and isinstance(new_enum, list):
        old_values = {repr(item) for item in old_enum}
        new_values = {repr(item) for item in new_enum}
        added = sorted(new_values - old_values)
        removed = sorted(old_values - new_values)
        if added:
            expansions.append(f"{prefix}enum added {', '.join(added)}")
        if removed:
            restrictions.append(f"{prefix}enum removed {', '.join(removed)}")
    elif old_enum != new_enum:
        if old_enum is None:
            restrictions.append(f"{prefix}enum constraint added")
        elif new_enum is None:
            expansions.append(f"{prefix}enum constraint removed")
        else:
            expansions.append(f"{prefix}enum constraint changed")
            restrictions.append(f"{prefix}enum constraint changed")

    old_additional = before.get("additionalProperties", True)
    new_additional = after.get("additionalProperties", True)
    if old_additional is False and new_additional is not False:
        expansions.append(f"{prefix}additionalProperties enabled")
    elif old_additional is not False and new_additional is False:
        restrictions.append(f"{prefix}additionalProperties disabled")
    elif old_additional != new_additional:
        expansions.append(f"{prefix}additionalProperties policy changed")
        restrictions.append(f"{prefix}additionalProperties policy changed")

    before_props = before.get("properties", {}) if isinstance(before.get("properties", {}), dict) else {}
    after_props = after.get("properties", {}) if isinstance(after.get("properties", {}), dict) else {}
    before_required = set(before.get("required", []) if isinstance(before.get("required", []), list) else [])
    after_required = set(after.get("required", []) if isinstance(after.get("required", []), list) else [])

    for name in sorted(after_props.keys() - before_props.keys()):
        qualifier = "required" if name in after_required else "optional"
        expansions.append(f"{prefix}new {qualifier} input property: {name}")
        if name in after_required:
            restrictions.append(f"{prefix}new required input property: {name}")
    for name in sorted(before_props.keys() - after_props.keys()):
        restrictions.append(f"{prefix}input property removed: {name}")
    for name in sorted(before_required - after_required):
        expansions.append(f"{prefix}input property no longer required: {name}")
    for name in sorted(after_required - before_required):
        restrictions.append(f"{prefix}input property newly required: {name}")

    for name in sorted(before_props.keys() & after_props.keys()):
        old = before_props[name]
        new = after_props[name]
        if isinstance(old, dict) and isinstance(new, dict):
            nested_expansions, nested_restrictions = _schema_directions(
                old,
                new,
                path=f"{prefix}properties.{name}".strip("."),
                depth=depth + 1,
            )
            expansions.extend(nested_expansions)
            restrictions.extend(nested_restrictions)
        elif old != new:
            expansions.append(f"{prefix}properties.{name} changed")
            restrictions.append(f"{prefix}properties.{name} changed")

    for key in ("minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties"):
        _compare_lower_bound(before, after, key, prefix, expansions, restrictions)
    for key in ("maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties"):
        _compare_upper_bound(before, after, key, prefix, expansions, restrictions)

    old_pattern = before.get("pattern")
    new_pattern = after.get("pattern")
    if old_pattern != new_pattern:
        if old_pattern is None:
            restrictions.append(f"{prefix}pattern constraint added")
        elif new_pattern is None:
            expansions.append(f"{prefix}pattern constraint removed")
        else:
            expansions.append(f"{prefix}pattern constraint changed")
            restrictions.append(f"{prefix}pattern constraint changed")

    old_items = before.get("items")
    new_items = after.get("items")
    if isinstance(old_items, dict) and isinstance(new_items, dict):
        nested_expansions, nested_restrictions = _schema_directions(
            old_items,
            new_items,
            path=f"{prefix}items".strip("."),
            depth=depth + 1,
        )
        expansions.extend(nested_expansions)
        restrictions.extend(nested_restrictions)
    elif old_items != new_items:
        expansions.append(f"{prefix}items schema changed")
        restrictions.append(f"{prefix}items schema changed")

    recognized = {
        "$schema",
        "$id",
        "title",
        "description",
        "default",
        "examples",
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minimum",
        "exclusiveMinimum",
        "maximum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
    }
    changed_unknown = sorted(
        key
        for key in (set(before) | set(after)) - recognized
        if before.get(key) != after.get(key)
    )
    if changed_unknown:
        summary = f"{prefix}unclassified schema keywords changed: {', '.join(changed_unknown)}"
        expansions.append(summary)
        restrictions.append(summary)

    for key in ("const", "format", "uniqueItems"):
        if before.get(key) != after.get(key):
            summary = f"{prefix}{key} changed"
            expansions.append(summary)
            restrictions.append(summary)

    return list(dict.fromkeys(expansions)), list(dict.fromkeys(restrictions))


def _tool_is_critical(tool: dict[str, Any]) -> bool:
    return bool(tool.get("destructive", False)) or str(tool.get("risk", "")).lower() == "critical"


def compare_manifests(baseline: dict[str, Any], candidate: dict[str, Any]) -> ChangeSet:
    changes: list[Change] = []

    if baseline.get("agent") != candidate.get("agent"):
        changes.append(
            Change(
                ChangeType.AGENT_CONFIG_CHANGED,
                "agent",
                Severity.HIGH,
                "agent identity or configuration changed",
                before_digest=digest(baseline.get("agent")),
                after_digest=digest(candidate.get("agent")),
            )
        )

    baseline_runtime = baseline.get("runtime", {})
    candidate_runtime = candidate.get("runtime", {})
    if baseline_runtime.get("provider") != candidate_runtime.get("provider"):
        changes.append(
            Change(
                ChangeType.PROVIDER_CHANGED,
                "runtime.provider",
                Severity.HIGH,
                "model provider changed",
                before_digest=digest(baseline_runtime.get("provider")),
                after_digest=digest(candidate_runtime.get("provider")),
            )
        )
    if baseline_runtime.get("model") != candidate_runtime.get("model"):
        changes.append(
            Change(
                ChangeType.MODEL_CHANGED,
                "runtime.model",
                Severity.HIGH,
                "requested model changed",
                before_digest=digest(baseline_runtime.get("model")),
                after_digest=digest(candidate_runtime.get("model")),
            )
        )

    baseline_instructions = baseline.get("instructions")
    candidate_instructions = candidate.get("instructions")
    if baseline_instructions != candidate_instructions:
        changes.append(
            Change(
                ChangeType.SYSTEM_INSTRUCTION_CHANGED,
                "instructions",
                Severity.HIGH,
                "system instructions changed",
                before_digest=digest(baseline_instructions),
                after_digest=digest(candidate_instructions),
            )
        )

    old_tools = _tool_map(baseline)
    new_tools = _tool_map(candidate)
    for name in sorted(new_tools.keys() - old_tools.keys()):
        tool = new_tools[name]
        changes.append(
            Change(
                ChangeType.TOOL_ADDED,
                f"tools.{name}",
                Severity.CRITICAL if _tool_is_critical(tool) else Severity.HIGH,
                f"tool added: {name}",
                tool=name,
                capability=name,
                after_digest=digest(tool),
                metadata={"destructive": bool(tool.get("destructive", False)), "risk": tool.get("risk")},
            )
        )
    for name in sorted(old_tools.keys() - new_tools.keys()):
        changes.append(
            Change(
                ChangeType.TOOL_REMOVED,
                f"tools.{name}",
                Severity.HIGH,
                f"tool removed: {name}",
                tool=name,
                capability=name,
                before_digest=digest(old_tools[name]),
            )
        )
    for name in sorted(old_tools.keys() & new_tools.keys()):
        old = old_tools[name]
        new = new_tools[name]
        if old.get("description") != new.get("description"):
            changes.append(
                Change(
                    ChangeType.TOOL_DESCRIPTION_CHANGED,
                    f"tools.{name}.description",
                    Severity.HIGH,
                    f"tool description changed: {name}",
                    tool=name,
                    capability=name,
                    before_digest=digest(old.get("description")),
                    after_digest=digest(new.get("description")),
                )
            )

        old_safety = {"risk": old.get("risk"), "destructive": old.get("destructive", False)}
        new_safety = {"risk": new.get("risk"), "destructive": new.get("destructive", False)}
        if old_safety != new_safety:
            old_rank = _RISK_RANK.get(str(old_safety["risk"]), 0)
            new_rank = _RISK_RANK.get(str(new_safety["risk"]), 0)
            weakened = new_rank < old_rank or (
                bool(old_safety["destructive"]) and not bool(new_safety["destructive"])
            )
            changes.append(
                Change(
                    ChangeType.TOOL_SAFETY_METADATA_CHANGED,
                    f"tools.{name}.safety",
                    Severity.CRITICAL if weakened else Severity.HIGH,
                    f"tool safety metadata changed: {name}",
                    tool=name,
                    capability=name,
                    before_digest=digest(old_safety),
                    after_digest=digest(new_safety),
                    metadata={"metadata_weakened": weakened},
                )
            )

        old_schema = old.get("input_schema", {})
        new_schema = new.get("input_schema", {})
        if old_schema != new_schema:
            expansions, restrictions = _schema_directions(old_schema, new_schema)
            if expansions and not restrictions:
                change_type = ChangeType.TOOL_INPUT_SCHEMA_EXPANDED
                reasons = expansions
            elif restrictions and not expansions:
                change_type = ChangeType.TOOL_INPUT_SCHEMA_RESTRICTED
                reasons = restrictions
            else:
                change_type = ChangeType.TOOL_SCHEMA_CHANGED
                reasons = expansions + restrictions or [
                    "schema changed without a recognized semantic direction"
                ]
            changes.append(
                Change(
                    change_type,
                    f"tools.{name}.input_schema",
                    Severity.HIGH,
                    f"tool input schema changed: {name}",
                    tool=name,
                    capability=name,
                    before_digest=digest(old_schema),
                    after_digest=digest(new_schema),
                    metadata={
                        "expansion_reasons": expansions,
                        "restriction_reasons": restrictions,
                        "reasons": list(dict.fromkeys(reasons)),
                    },
                )
            )

        old_extra = {key: old[key] for key in old.keys() - _TOOL_KNOWN_FIELDS}
        new_extra = {key: new[key] for key in new.keys() - _TOOL_KNOWN_FIELDS}
        if old_extra != new_extra:
            changes.append(
                Change(
                    ChangeType.TOOL_CONFIGURATION_CHANGED,
                    f"tools.{name}.configuration",
                    Severity.HIGH,
                    f"unclassified tool configuration changed: {name}",
                    tool=name,
                    capability=name,
                    before_digest=digest(old_extra),
                    after_digest=digest(new_extra),
                    metadata={"changed_fields": sorted(set(old_extra) | set(new_extra))},
                )
            )

    baseline_policy = baseline.get("policy")
    candidate_policy = candidate.get("policy")
    if baseline_policy != candidate_policy:
        expanded_tools: list[str] = []
        if isinstance(baseline_policy, dict) and isinstance(candidate_policy, dict):
            old_allowed = baseline_policy.get("allowed_tools", [])
            new_allowed = candidate_policy.get("allowed_tools", [])
            if isinstance(old_allowed, list) and isinstance(new_allowed, list):
                expanded_tools = sorted(set(map(str, new_allowed)) - set(map(str, old_allowed)))
        changes.append(
            Change(
                ChangeType.POLICY_SCOPE_EXPANDED if expanded_tools else ChangeType.POLICY_CHANGED,
                "policy",
                Severity.CRITICAL if expanded_tools else Severity.HIGH,
                "policy scope expanded" if expanded_tools else "policy configuration changed",
                before_digest=digest(baseline_policy),
                after_digest=digest(candidate_policy),
                metadata={"added_allowed_tools": expanded_tools},
            )
        )

    for field, change_type in (
        ("mcp", ChangeType.MCP_SERVER_CHANGED),
        ("retrieval", ChangeType.RETRIEVAL_CORPUS_CHANGED),
        ("source", ChangeType.SOURCE_CODE_CHANGED),
        ("environment", ChangeType.RUNTIME_CONFIG_CHANGED),
    ):
        if baseline.get(field) != candidate.get(field):
            changes.append(
                Change(
                    change_type,
                    field,
                    Severity.HIGH,
                    f"{field} configuration changed",
                    before_digest=digest(baseline.get(field)),
                    after_digest=digest(candidate.get(field)),
                )
            )

    handled = {
        "agent",
        "runtime",
        "instructions",
        "tools",
        "mcp",
        "policy",
        "retrieval",
        "source",
        "environment",
    }
    all_keys = set(baseline) | set(candidate)
    for key in sorted(all_keys - handled):
        if baseline.get(key) != candidate.get(key):
            changes.append(
                Change(
                    ChangeType.UNCLASSIFIED_CHANGE,
                    key,
                    Severity.HIGH,
                    f"unclassified manifest change: {key}",
                    before_digest=digest(baseline.get(key)),
                    after_digest=digest(candidate.get(key)),
                )
            )

    if baseline_runtime != candidate_runtime:
        known = {"provider", "model"}
        runtime_keys = set(baseline_runtime) | set(candidate_runtime)
        if any(
            baseline_runtime.get(key) != candidate_runtime.get(key)
            for key in runtime_keys
            if key not in known
        ):
            changes.append(
                Change(
                    ChangeType.RUNTIME_CONFIG_CHANGED,
                    "runtime",
                    Severity.HIGH,
                    "runtime configuration changed",
                    before_digest=digest(baseline_runtime),
                    after_digest=digest(candidate_runtime),
                )
            )

    return ChangeSet(digest(baseline), digest(candidate), tuple(changes))
