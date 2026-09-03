from __future__ import annotations

import json

from agents.strict_schema import ensure_strict_json_schema

PREFIX = "PROOFDIFF_PROBE="


def _chained_ref_observation() -> tuple[bool, dict]:
    schema = {
        "$defs": {
            "Inner": {"type": "string"},
            "Outer": {"$ref": "#/$defs/Inner"},
        },
        "type": "object",
        "properties": {
            "a": {
                "$ref": "#/$defs/Outer",
                "description": "desc",
            }
        },
    }
    result = ensure_strict_json_schema(schema)
    observed = result["properties"]["a"]
    preserved = (
        observed.get("type") == "string"
        and observed.get("description") == "desc"
        and "$ref" not in observed
    )
    return preserved, result


def _direct_ref_preserved() -> bool:
    schema = {
        "$defs": {"Inner": {"type": "string"}},
        "type": "object",
        "properties": {
            "a": {
                "$ref": "#/$defs/Inner",
                "description": "desc",
            }
        },
    }
    result = ensure_strict_json_schema(schema)
    observed = result["properties"]["a"]
    return (
        observed.get("type") == "string"
        and observed.get("description") == "desc"
        and "$ref" not in observed
    )


def _invalid_ref_rejected() -> bool:
    schema = {
        "type": "object",
        "properties": {"a": {"$ref": "invalid", "description": "desc"}},
    }
    try:
        ensure_strict_json_schema(schema)
    except ValueError:
        return True
    return False


def main() -> int:
    chained_ok, strict_schema = _chained_ref_observation()
    payload = {
        "chained_ref_preserves_type": chained_ok,
        "direct_ref_preserves_type": _direct_ref_preserved(),
        "invalid_ref_rejected": _invalid_ref_rejected(),
        "strict_schema": strict_schema,
    }
    print(PREFIX + json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
