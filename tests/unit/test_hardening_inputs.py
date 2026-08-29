from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.engine import canonical, io, traces
from proofdiff.engine.canonical import digest, is_safe_secret_reference, is_secret_key, redact_secrets
from proofdiff.engine.contracts import parse_contract
from proofdiff.engine.io import load_jsonl, load_object, write_json
from proofdiff.engine.manifest import snapshot_manifest, unwrap_snapshot, validate_manifest
from proofdiff.engine.traces import load_traces, parse_trace


def base_manifest() -> dict[str, object]:
    return {
        "agent": {"name": "agent"},
        "runtime": {"provider": "fixture", "model": "v1"},
        "tools": [
            {
                "name": "lookup",
                "description": "Read data",
                "risk": "low",
                "destructive": False,
                "input_schema": {
                    "type": "object",
                    "properties": {"access_token": {"type": "string"}},
                },
            }
        ],
    }


def valid_contract() -> dict[str, object]:
    return {
        "id": "contract.one",
        "title": "Contract one",
        "risk": "high",
        "tags": ["smoke"],
        "always_run": True,
        "covers": {"tools": ["lookup"]},
        "expect": {"required_tools": ["lookup"]},
    }


def test_strict_json_rejects_duplicate_keys_nonfinite_and_nonobject(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(InputError, match="duplicate object key"):
        load_object(duplicate)

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value": NaN}', encoding="utf-8")
    with pytest.raises(InputError, match="non-finite"):
        load_object(nonfinite)

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(InputError, match="document root"):
        load_object(array)


def test_io_rejects_symlinks_and_jsonl_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(InputError, match="symbolic-link"):
        load_object(link)

    records = tmp_path / "records.jsonl"
    records.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    monkeypatch.setattr(io, "MAX_JSONL_RECORDS", 1)
    with pytest.raises(InputError, match="exceeds 1 records"):
        load_jsonl(records)

    records.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(io, "MAX_JSONL_RECORDS", 100_000)
    with pytest.raises(InputError, match="expected JSON object"):
        load_jsonl(records)


def test_atomic_json_writer_rejects_nonfinite(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="non-finite"):
        write_json(tmp_path / "bad.json", {"value": math.inf})
    assert not (tmp_path / "bad.json").exists()


def test_secret_protection_preserves_schema_names_and_detects_changes() -> None:
    manifest = base_manifest()
    manifest["runtime"] = {
        "provider": "fixture",
        "model": "v1",
        "api_token": "raw-secret-value",
        "credential_ref": "env:AGENT_CREDENTIAL",
    }
    validated = validate_manifest(manifest)
    runtime = validated["runtime"]
    assert isinstance(runtime, dict)
    assert runtime["api_token"] == {"$secret_digest": digest("raw-secret-value")}
    assert runtime["credential_ref"] == "env:AGENT_CREDENTIAL"
    schema = validated["tools"][0]["input_schema"]  # type: ignore[index]
    assert "access_token" in schema["properties"]

    manifest_with_schema_secret = json.loads(json.dumps(manifest))
    manifest_with_schema_secret["tools"][0]["input_schema"]["properties"]["access_token"] = {
        "type": "string",
        "default": "schema-secret",
        "examples": ["another-schema-secret"],
    }
    protected_schema = validate_manifest(manifest_with_schema_secret)["tools"][0]["input_schema"]
    secret_property = protected_schema["properties"]["access_token"]
    assert secret_property["default"] == {"$secret_digest": digest("schema-secret")}
    assert secret_property["examples"] == {
        "$secret_digest": digest(["another-schema-secret"])
    }

    changed = json.loads(json.dumps(manifest))
    changed["runtime"]["api_token"] = "different-secret"  # type: ignore[index]
    assert validate_manifest(changed)["runtime"] != validated["runtime"]


def test_secret_helpers_cover_references_and_nested_redaction() -> None:
    assert is_secret_key("API-Key")
    assert not is_secret_key("model")
    assert is_safe_secret_reference("secret://team/key")
    assert is_safe_secret_reference("${API_KEY}")
    assert not is_safe_secret_reference("plaintext")
    assert redact_secrets({"token": "x", "nested": [{"password": "y"}]}) == {
        "token": "<redacted>",
        "nested": [{"password": "<redacted>"}],
    }


def test_manifest_rejects_invalid_tool_metadata() -> None:
    manifest = base_manifest()
    tool = manifest["tools"][0]  # type: ignore[index]
    tool["risk"] = "unknown"
    with pytest.raises(InputError, match="risk must be"):
        validate_manifest(manifest)

    manifest = base_manifest()
    manifest["tools"][0]["destructive"] = "false"  # type: ignore[index]
    with pytest.raises(InputError, match="destructive must be a boolean"):
        validate_manifest(manifest)

    manifest = base_manifest()
    manifest["tools"][0]["description"] = 7  # type: ignore[index]
    with pytest.raises(InputError, match="description must be a string"):
        validate_manifest(manifest)

    manifest = base_manifest()
    manifest["tools"].append(dict(manifest["tools"][0]))  # type: ignore[union-attr,index]
    with pytest.raises(InputError, match="duplicate tool name"):
        validate_manifest(manifest)


def test_snapshot_supports_legacy_shape_and_rejects_invalid_shapes(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(base_manifest()), encoding="utf-8")
    snapshot_file = tmp_path / "snapshot.json"
    recorded = snapshot_manifest(manifest_file, snapshot_file)
    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert unwrap_snapshot(snapshot)["agent"] == {"name": "agent"}
    legacy = {"digest": recorded, "manifest": snapshot["manifest"]}
    assert unwrap_snapshot(legacy)["runtime"]["provider"] == "fixture"

    with pytest.raises(InputError, match="unsupported snapshot"):
        unwrap_snapshot({"schema_version": "2", "digest": recorded, "manifest": snapshot["manifest"]})
    with pytest.raises(InputError, match="digest must be a string"):
        unwrap_snapshot({"digest": 3, "manifest": snapshot["manifest"]})
    with pytest.raises(InputError, match="optional schema_version"):
        unwrap_snapshot({"digest": recorded, "manifest": snapshot["manifest"], "extra": True})


def test_contract_parser_rejects_ambiguous_or_nonexecutable_contracts() -> None:
    value = valid_contract()
    value["unexpected"] = True
    with pytest.raises(InputError, match="unknown fields"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["always_run"] = "true"
    with pytest.raises(InputError, match="must be a boolean"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["tags"] = ["smoke", "smoke"]
    with pytest.raises(InputError, match="duplicates"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["covers"] = {}
    value["always_run"] = False
    with pytest.raises(InputError, match="no coverage"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["expect"] = {}
    with pytest.raises(InputError, match="no executable expectations"):
        parse_contract(value, "memory")


def test_contract_parser_rejects_conflicts_and_nonfinite_budget() -> None:
    value = valid_contract()
    value["expect"] = {"required_tools": ["lookup"], "forbidden_tools": ["lookup"]}
    with pytest.raises(InputError, match="requires and forbids"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["expect"] = {"required_tools": ["lookup"], "max_tool_calls": {"lookup": 0}}
    with pytest.raises(InputError, match="zero call budget"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["expect"] = {"output_contains": ["secret"], "output_not_contains": ["SECRET"]}
    with pytest.raises(InputError, match="requires and forbids output"):
        parse_contract(value, "memory")

    value = valid_contract()
    value["expect"] = {"budgets": {"cost": math.nan}}
    with pytest.raises(InputError, match="finite and non-negative"):
        parse_contract(value, "memory")


def test_trace_limits_unknown_fields_and_nonfinite_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(InputError, match="unknown fields"):
        parse_trace({"case_id": "case", "events": [], "extra": 1}, "memory")
    with pytest.raises(InputError, match="event contains unknown"):
        parse_trace({"case_id": "case", "events": [{"type": "tool_call", "extra": 1}]}, "memory")
    with pytest.raises(InputError, match="non-finite"):
        parse_trace({"case_id": "case", "events": [], "metrics": {"cost": math.inf}}, "memory")

    monkeypatch.setattr(traces, "MAX_TRACE_EVENTS", 1)
    with pytest.raises(InputError, match="exceeds 1 events"):
        parse_trace(
            {"case_id": "case", "events": [{"type": "a"}, {"type": "b"}]},
            "memory",
        )
    monkeypatch.setattr(traces, "MAX_OUTPUT_CHARS", 3)
    with pytest.raises(InputError, match="output exceeds"):
        parse_trace({"case_id": "case", "events": [], "output": "long"}, "memory")


def test_load_traces_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    path = tmp_path / "traces.jsonl"
    path.write_text(
        '{"case_id":"same","events":[]}\n{"case_id":"same","events":[]}\n',
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="duplicate trace case_id"):
        load_traces(path)


def test_canonical_collection_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canonical, "MAX_COLLECTION_ITEMS", 1)
    with pytest.raises(InputError, match="collection exceeds"):
        canonical.normalize([1, 2])
    with pytest.raises(InputError, match="mapping exceeds"):
        canonical.normalize({"a": 1, "b": 2})


def test_manifest_rejects_non_string_mapping_keys_before_secret_processing() -> None:
    manifest = base_manifest()
    manifest["runtime"] = {1: "invalid"}  # type: ignore[dict-item]
    with pytest.raises(InputError, match="mapping keys must be strings"):
        validate_manifest(manifest)


def test_input_rejects_symbolic_link_ancestor(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "document.json").write_text("{}\n", encoding="utf-8")
    link = tmp_path / "linked-directory"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(InputError, match="symbolic-link path components"):
        load_object(link / "document.json")
