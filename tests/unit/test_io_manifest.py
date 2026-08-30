from __future__ import annotations

import json
from pathlib import Path

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.engine.io import load_document, load_jsonl, load_object, write_json, write_jsonl
from proofdiff.engine.manifest import load_manifest, snapshot_manifest, unwrap_snapshot, validate_manifest


def valid_manifest() -> dict[str, object]:
    return {
        "agent": {"name": "a"},
        "runtime": {"provider": "fixture"},
        "tools": [{"name": "lookup", "input_schema": {"type": "object"}}],
    }


def test_json_io_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "value.json"
    write_json(path, {"b": 2, "a": 1})
    assert load_object(path) == {"a": 1, "b": 2}

    jsonl = tmp_path / "rows.jsonl"
    write_jsonl(jsonl, [{"id": 1}, {"id": 2}])
    assert load_jsonl(jsonl) == [{"id": 1}, {"id": 2}]


def test_load_document_and_root_errors(tmp_path: Path) -> None:
    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    assert load_document(list_path) == []
    with pytest.raises(InputError, match="document root"):
        load_object(list_path)

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(InputError, match="invalid document"):
        load_document(bad)


def test_jsonl_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("[]\n", encoding="utf-8")
    with pytest.raises(InputError, match="expected JSON object"):
        load_jsonl(bad)
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("{\n", encoding="utf-8")
    with pytest.raises(InputError, match="invalid JSONL"):
        load_jsonl(malformed)


def test_manifest_validation_and_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(valid_manifest()), encoding="utf-8")
    loaded = load_manifest(source)
    assert loaded["agent"] == {"name": "a"}
    destination = tmp_path / "snapshot.json"
    recorded = snapshot_manifest(source, destination)
    snapshot = load_object(destination)
    assert snapshot["digest"] == recorded
    assert unwrap_snapshot(snapshot) == loaded


def test_manifest_validation_errors() -> None:
    with pytest.raises(InputError, match="missing required"):
        validate_manifest({})
    with pytest.raises(InputError, match=r"manifest\.agent"):
        validate_manifest({"agent": [], "runtime": {}, "tools": []})
    with pytest.raises(InputError, match=r"manifest\.runtime"):
        validate_manifest({"agent": {}, "runtime": [], "tools": []})
    with pytest.raises(InputError, match=r"manifest\.tools"):
        validate_manifest({"agent": {}, "runtime": {}, "tools": {}})
    with pytest.raises(InputError, match="must be an object"):
        validate_manifest({"agent": {}, "runtime": {}, "tools": ["x"]})
    with pytest.raises(InputError, match="name must be non-empty"):
        validate_manifest({"agent": {}, "runtime": {}, "tools": [{}]})
    with pytest.raises(InputError, match="duplicate tool name"):
        validate_manifest(
            {
                "agent": {},
                "runtime": {},
                "tools": [
                    {"name": "x", "input_schema": {}},
                    {"name": "x", "input_schema": {}},
                ],
            }
        )
    with pytest.raises(InputError, match="input_schema"):
        validate_manifest({"agent": {}, "runtime": {}, "tools": [{"name": "x", "input_schema": []}]})


def test_snapshot_digest_mismatch_rejected() -> None:
    with pytest.raises(InputError, match="digest does not match"):
        unwrap_snapshot({"digest": "sha256:bad", "manifest": valid_manifest()})
    with pytest.raises(InputError, match="snapshot manifest"):
        unwrap_snapshot({"manifest": []})
