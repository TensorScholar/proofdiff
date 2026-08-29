from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from proofdiff.domain.errors import InputError
from proofdiff.engine.canonical import digest, is_safe_secret_reference, is_secret_key, normalize
from proofdiff.engine.io import load_object, write_json

REQUIRED_TOP_LEVEL = {"agent", "runtime", "tools"}
TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
VALID_TOOL_RISKS = {"low", "medium", "high", "critical"}


def _is_secret_digest(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"$secret_digest"}
        and isinstance(value["$secret_digest"], str)
        and DIGEST_PATTERN.fullmatch(value["$secret_digest"]) is not None
    )


def _protected_secret(value: Any) -> Any:
    if is_safe_secret_reference(value) or _is_secret_digest(value):
        return value
    return {"$secret_digest": digest(value)}


def _protect_schema_values(value: Any, *, secret_property: bool = False) -> Any:
    """Protect credential literals embedded in JSON Schema defaults and examples.

    Property names remain intact because they are interface declarations. Literal values attached
    to a secret-like property are one-way digested so snapshots preserve change detection without
    persisting the credential itself.
    """

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "properties" and isinstance(item, dict):
                result[key] = {
                    property_name: _protect_schema_values(
                        property_schema,
                        secret_property=is_secret_key(property_name),
                    )
                    for property_name, property_schema in item.items()
                }
            elif secret_property and key in {"const", "default", "enum", "examples"}:
                result[key] = _protected_secret(item)
            else:
                result[key] = _protect_schema_values(item, secret_property=secret_property)
        return result
    if isinstance(value, list):
        return [_protect_schema_values(item, secret_property=secret_property) for item in value]
    return value


def _protect_secret_values(value: Any) -> Any:
    """Replace raw secret-like configuration values with one-way digests."""

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "input_schema":
                result[key] = _protect_schema_values(item)
            elif is_secret_key(key):
                result[key] = _protected_secret(item)
            else:
                result[key] = _protect_secret_values(item)
        return result
    if isinstance(value, list):
        return [_protect_secret_values(item) for item in value]
    return value


def _validate_tool(tool: Any, index: int, names: set[str]) -> None:
    if not isinstance(tool, dict):
        raise InputError(f"manifest.tools[{index}] must be an object")
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise InputError(f"manifest.tools[{index}].name must be non-empty")
    if TOOL_NAME.fullmatch(name) is None:
        raise InputError(f"manifest.tools[{index}].name must match {TOOL_NAME.pattern!r}")
    if name in names:
        raise InputError(f"duplicate tool name: {name}")
    names.add(name)
    schema = tool.get("input_schema", {})
    if not isinstance(schema, dict):
        raise InputError(f"tool {name} input_schema must be an object")
    description = tool.get("description")
    if description is not None and not isinstance(description, str):
        raise InputError(f"tool {name} description must be a string")
    risk = tool.get("risk")
    if risk is not None and risk not in VALID_TOOL_RISKS:
        raise InputError(f"tool {name} risk must be one of {sorted(VALID_TOOL_RISKS)}")
    destructive = tool.get("destructive")
    if destructive is not None and not isinstance(destructive, bool):
        raise InputError(f"tool {name} destructive must be a boolean")


def validate_manifest(value: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize(value)
    if not isinstance(normalized, dict):
        raise InputError("manifest must be an object")
    missing = sorted(REQUIRED_TOP_LEVEL - normalized.keys())
    if missing:
        raise InputError(f"manifest missing required keys: {', '.join(missing)}")
    if not isinstance(normalized["agent"], dict):
        raise InputError("manifest.agent must be an object")
    if not isinstance(normalized["runtime"], dict):
        raise InputError("manifest.runtime must be an object")
    if not isinstance(normalized["tools"], list):
        raise InputError("manifest.tools must be an array")
    names: set[str] = set()
    for index, tool in enumerate(normalized["tools"]):
        _validate_tool(tool, index, names)
    protected = _protect_secret_values(normalized)
    if not isinstance(protected, dict):
        raise InputError("manifest protection produced an invalid object")
    return protected


def load_manifest(path: str | Path) -> dict[str, Any]:
    return validate_manifest(load_object(path))


def snapshot_manifest(source: str | Path, destination: str | Path) -> str:
    manifest = load_manifest(source)
    manifest_digest = digest(manifest)
    payload = {"schema_version": "1", "digest": manifest_digest, "manifest": manifest}
    write_json(destination, payload)
    return manifest_digest


def unwrap_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    if "manifest" in value and not isinstance(value.get("manifest"), dict):
        raise InputError("snapshot manifest must be an object")
    is_snapshot = "schema_version" in value or "digest" in value
    if not is_snapshot:
        return validate_manifest(value)
    keys = set(value)
    if keys not in ({"digest", "manifest"}, {"schema_version", "digest", "manifest"}):
        raise InputError("snapshot must contain digest and manifest, with optional schema_version")
    if value.get("schema_version", "1") != "1":
        raise InputError("unsupported snapshot schema_version")
    recorded = value.get("digest")
    if not isinstance(recorded, str):
        raise InputError("snapshot digest must be a string")
    manifest = value.get("manifest")
    if not isinstance(manifest, dict):
        raise InputError("snapshot manifest must be an object")
    validated = validate_manifest(manifest)
    actual = digest(validated)
    if recorded != actual:
        raise InputError("snapshot digest does not match manifest content")
    return validated
