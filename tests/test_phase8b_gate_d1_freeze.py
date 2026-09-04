from __future__ import annotations

import copy
import json

from benchmarks.phase8b import validate_gate_d1 as d1f


def _record() -> dict[str, object]:
    return json.loads(d1f.GATE_D1_PATH.read_text(encoding="utf-8"))


def test_frozen_gate_d1_record_is_valid() -> None:
    assert d1f.validate_gate_d1(_record()) == []


def test_gate_d1_rejects_observation_or_d2_authorization_drift() -> None:
    observed = copy.deepcopy(_record())
    observed["historical_candidate_observation_state_at_freeze"] = "observed"
    assert any("must precede" in finding for finding in d1f.validate_gate_d1(observed))

    authorized = copy.deepcopy(_record())
    authorized["d2_execution_authorized"] = True
    assert any("must not itself authorize D2" in finding for finding in d1f.validate_gate_d1(authorized))


def test_gate_d1_rejects_frozen_dependency_drift() -> None:
    record = copy.deepcopy(_record())
    record["frozen_repository_blobs"]["candidate"]["git_blob_sha"] = "0" * 40
    findings = d1f.validate_gate_d1(record)
    assert any("current repository blob differs" in finding for finding in findings)
    assert any("D1 identity no longer matches frozen Gate D0 identity" in finding for finding in findings)

    record = copy.deepcopy(_record())
    record["frozen_repository_blobs"]["d1_validator"]["git_blob_sha"] = "0" * 40
    assert any("current repository blob differs" in finding for finding in d1f.validate_gate_d1(record))


def test_gate_d1_rejects_authoritative_artifact_identity_drift() -> None:
    record = copy.deepcopy(_record())
    record["authoritative_artifact"]["artifact_id"] = 1
    assert any("artifact identity drifted" in finding for finding in d1f.validate_gate_d1(record))

    record = copy.deepcopy(_record())
    record["authoritative_artifact"]["sha256"] = "0" * 64
    findings = d1f.validate_gate_d1(record)
    assert any("artifact SHA-256 drifted" in finding for finding in findings)
    assert any("downloaded ZIP digest" in finding for finding in findings)


def test_gate_d1_rejects_inner_bundle_digest_or_count_drift() -> None:
    record = copy.deepcopy(_record())
    record["candidate_visible_bundle"]["input_manifest_digest"] = "0" * 64
    assert any("input_manifest_digest drifted" in finding for finding in d1f.validate_gate_d1(record))

    record = copy.deepcopy(_record())
    record["candidate_visible_bundle"]["case_direction_count"] = 45
    assert any("case-direction count drifted" in finding for finding in d1f.validate_gate_d1(record))


def test_gate_d1_rejects_failed_audit_or_weakened_d2_contract() -> None:
    record = copy.deepcopy(_record())
    record["out_of_workflow_download_audit"]["checks"]["canonical_json_bytes"] = "failed"
    assert any("audit check did not pass" in finding for finding in d1f.validate_gate_d1(record))

    record = copy.deepcopy(_record())
    record["d2_consumption_contract"]["upstream_rematerialization_forbidden"] = False
    assert any("must require upstream_rematerialization_forbidden" in finding for finding in d1f.validate_gate_d1(record))

    record = copy.deepcopy(_record())
    record["d2_consumption_contract"]["ground_truth_visible_to_candidate"] = True
    assert any("must forbid ground_truth_visible_to_candidate" in finding for finding in d1f.validate_gate_d1(record))


def test_gate_d1_rejects_timestamp_or_next_gate_drift() -> None:
    record = copy.deepcopy(_record())
    record["frozen_at"] = "not-a-time"
    assert any("ISO-8601 UTC" in finding for finding in d1f.validate_gate_d1(record))

    record = copy.deepcopy(_record())
    record["next_gate"]["state"] = "authorized"
    assert any("D2 must remain blocked" in finding for finding in d1f.validate_gate_d1(record))
