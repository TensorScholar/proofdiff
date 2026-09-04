from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "benchmarks" / "phase8b"
GATE_D1_PATH = PHASE / "gate_d1.json"
GATE_D_PATH = PHASE / "gate_d.json"
CORPUS_PATH = PHASE / "corpus.json"

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN_KEY_DIRECTIONS = ("forward", "reverse")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _parse_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _evaluation_case(case: dict[str, Any]) -> bool:
    return (case.get("arm") == "historical" and case.get("eligibility") == "qualified") or (
        case.get("arm") == "control" and case.get("eligibility") == "control"
    )


def _expect(findings: list[str], condition: bool, message: str) -> None:
    if not condition:
        findings.append(message)


def validate_gate_d1(record: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    gate_d = _load_json(GATE_D_PATH)
    corpus = _load_json(CORPUS_PATH)

    _expect(findings, record.get("schema_version") == "1.0", "schema_version must be 1.0")
    _expect(findings, record.get("phase") == "8B", "phase must be 8B")
    _expect(findings, record.get("gate") == "D", "gate must be D")
    _expect(findings, record.get("subgate") == "D1", "subgate must be D1")
    _expect(findings, record.get("freeze_status") == "frozen", "Gate D1 must be frozen")
    _expect(
        findings,
        record.get("historical_candidate_observation_state_at_freeze") == "unobserved",
        "Gate D1 freeze must precede any historical/control candidate observation",
    )
    _expect(findings, record.get("d2_execution_authorized") is False, "D1 freeze must not itself authorize D2")
    _expect(findings, gate_d.get("protocol_status") == "frozen", "Gate D protocol must remain frozen")
    _expect(
        findings,
        gate_d.get("observation_state_at_protocol_creation") == "unobserved",
        "Gate D protocol creation observation state drifted",
    )

    try:
        frozen_at = _parse_utc(record.get("frozen_at"), field="frozen_at")
    except ValueError as exc:
        findings.append(str(exc))
        frozen_at = None

    blobs = record.get("frozen_repository_blobs")
    if not isinstance(blobs, dict):
        return [*findings, "frozen_repository_blobs must be an object"]

    expected_paths = {
        "gate_d": "benchmarks/phase8b/gate_d.json",
        "corpus": "benchmarks/phase8b/corpus.json",
        "gate_b": "benchmarks/phase8b/gate_b.json",
        "static_rules": "benchmarks/phase8b/static_rules.json",
        "harness": "benchmarks/phase8b/harness.py",
        "methods": "benchmarks/phase8b/methods.py",
        "candidate": "benchmarks/phase8b/big_candidate.py",
        "materializer": "benchmarks/phase8b/materialize_gate_d_inputs.py",
        "d1_validator": "benchmarks/phase8b/validate_gate_d_inputs.py",
        "d1_workflow": ".github/workflows/phase8b-gate-d1.yml",
    }
    _expect(findings, set(blobs) == set(expected_paths), "frozen repository blob set drifted")

    for name, expected_path in expected_paths.items():
        item = blobs.get(name)
        if not isinstance(item, dict):
            findings.append(f"missing frozen blob record: {name}")
            continue
        _expect(findings, item.get("path") == expected_path, f"{name}: frozen path drifted")
        blob_sha = item.get("git_blob_sha")
        _expect(
            findings,
            isinstance(blob_sha, str) and bool(HEX40.fullmatch(blob_sha)),
            f"{name}: invalid Git blob SHA",
        )
        path = ROOT / expected_path
        if path.is_file() and isinstance(blob_sha, str):
            _expect(findings, _git_blob_sha(path) == blob_sha, f"{name}: current repository blob differs from D1 freeze")
        else:
            findings.append(f"{name}: frozen dependency path missing from repository")

    d0_inputs = gate_d.get("frozen_inputs", {})
    for name in ("corpus", "gate_b", "static_rules", "harness", "methods", "candidate"):
        d1_item = blobs.get(name, {})
        d0_item = d0_inputs.get(name, {}) if isinstance(d0_inputs, dict) else {}
        _expect(
            findings,
            isinstance(d1_item, dict)
            and isinstance(d0_item, dict)
            and d1_item.get("git_blob_sha") == d0_item.get("git_blob_sha"),
            f"{name}: D1 identity no longer matches frozen Gate D0 identity",
        )
    candidate = blobs.get("candidate", {})
    _expect(
        findings,
        isinstance(candidate, dict) and candidate.get("id") == d0_inputs.get("candidate", {}).get("id") == "minimal_big_v1",
        "candidate identity drifted",
    )

    artifact = record.get("authoritative_artifact")
    if not isinstance(artifact, dict):
        findings.append("authoritative_artifact must be an object")
    else:
        _expect(findings, artifact.get("repository") == "TensorScholar/proofdiff", "artifact repository drifted")
        _expect(
            findings,
            artifact.get("workflow_run_id") == 33896967976,
            "authoritative D1 workflow run identity drifted",
        )
        _expect(findings, artifact.get("artifact_id") == 9946174613, "authoritative artifact identity drifted")
        _expect(
            findings,
            artifact.get("artifact_name")
            == "phase8b-gate-d1-input-bundle-954cdea85d24ad606a168517686fa38d2cd21eca",
            "authoritative artifact name drifted",
        )
        _expect(findings, artifact.get("size_bytes") == 122641443, "authoritative artifact byte size drifted")
        digest = artifact.get("sha256")
        _expect(
            findings,
            isinstance(digest, str)
            and bool(HEX64.fullmatch(digest))
            and digest == "94a95e98e9faf2e8619ea521ac0b606d7303fc36840676cdbe489b0732f08440",
            "authoritative artifact SHA-256 drifted",
        )
        try:
            created_at = _parse_utc(artifact.get("created_at"), field="authoritative_artifact.created_at")
            expires_at = _parse_utc(artifact.get("expires_at"), field="authoritative_artifact.expires_at")
            if frozen_at is not None:
                _expect(findings, created_at <= frozen_at < expires_at, "D1 freeze timestamp must follow artifact creation and precede expiry")
            _expect(findings, created_at < expires_at, "artifact expiry must follow artifact creation")
        except ValueError as exc:
            findings.append(str(exc))

    bundle = record.get("candidate_visible_bundle")
    if not isinstance(bundle, dict):
        findings.append("candidate_visible_bundle must be an object")
    else:
        evaluation_cases = [
            case for case in corpus.get("cases", []) if isinstance(case, dict) and _evaluation_case(case)
        ]
        expected_case_count = len(evaluation_cases)
        _expect(findings, bundle.get("manifest_schema_version") == "1.1", "D1 manifest schema drifted")
        _expect(
            findings,
            bundle.get("bundle_format") == "canonical_candidate_payload_json_v1",
            "D1 bundle format drifted",
        )
        _expect(findings, bundle.get("candidate_id") == "minimal_big_v1", "D1 bundle candidate identity drifted")
        _expect(
            findings,
            bundle.get("calibration_freshness")
            == gate_d.get("execution_design", {}).get("candidate_calibration_freshness")
            == "not_yet_calibrated",
            "D1 bundle calibration state drifted",
        )
        _expect(findings, bundle.get("evaluation_case_count") == expected_case_count, "D1 evaluation case count drifted")
        _expect(
            findings,
            bundle.get("case_direction_count") == expected_case_count * len(RUN_KEY_DIRECTIONS),
            "D1 case-direction count drifted",
        )
        _expect(
            findings,
            bundle.get("payload_file_count") == bundle.get("case_direction_count"),
            "D1 payload file count must equal case-direction count",
        )
        expected_digests = {
            "candidate_payload_bundle_digest": "854ff2e2097673972c12a4ea57c49d00941af8591349961fb6fa05263ff8dc5c",
            "candidate_visible_payload_set_digest": "4e9ed3c35fa12e119b7dc3b46e053ca0f69828e825852b3ed3d93ad9b8926ca0",
            "input_manifest_digest": "79acf5265bf9ddd461379db1c12491d53811ad822ef25849b2443f7323ad3cc0",
        }
        for field, expected in expected_digests.items():
            value = bundle.get(field)
            _expect(
                findings,
                isinstance(value, str) and bool(HEX64.fullmatch(value)) and value == expected,
                f"{field} drifted",
            )

    audit = record.get("out_of_workflow_download_audit")
    if not isinstance(audit, dict):
        findings.append("out_of_workflow_download_audit must be an object")
    else:
        _expect(findings, audit.get("status") == "passed", "out-of-workflow audit must pass")
        _expect(findings, audit.get("audit_errors") == 0, "out-of-workflow audit must have zero errors")
        _expect(
            findings,
            audit.get("downloaded_zip_sha256") == artifact.get("sha256") if isinstance(artifact, dict) else False,
            "downloaded ZIP digest must equal authoritative artifact digest",
        )
        _expect(
            findings,
            audit.get("downloaded_zip_size_bytes") == artifact.get("size_bytes") if isinstance(artifact, dict) else False,
            "downloaded ZIP size must equal authoritative artifact size",
        )
        _expect(findings, audit.get("zip_file_count") == 47, "audited ZIP file count drifted")
        _expect(findings, audit.get("zip_symlink_count") == 0, "audited ZIP must contain no symlinks")
        checks = audit.get("checks")
        if not isinstance(checks, dict) or not checks:
            findings.append("audit checks must be a non-empty object")
        else:
            for name, state in checks.items():
                _expect(findings, state == "passed", f"audit check did not pass: {name}")

    contract = record.get("d2_consumption_contract")
    if not isinstance(contract, dict):
        findings.append("d2_consumption_contract must be an object")
    else:
        required_true = (
            "outer_zip_sha256_must_match",
            "safe_extraction_required",
            "closed_set_bundle_validation_required",
            "upstream_rematerialization_forbidden",
            "partial_result_tuning_forbidden",
        )
        for field in required_true:
            _expect(findings, contract.get(field) is True, f"D2 contract must require {field}")
        required_false = (
            "candidate_network_access",
            "candidate_filesystem_access_outside_payload",
            "candidate_git_metadata_access",
            "candidate_benchmark_metadata_access",
            "evaluator_manifest_visible_to_candidate",
            "case_id_visible_to_candidate",
            "ground_truth_visible_to_candidate",
        )
        for field in required_false:
            _expect(findings, contract.get(field) is False, f"D2 contract must forbid {field}")
        _expect(
            findings,
            contract.get("candidate_input") == "raw canonical payload JSON only",
            "D2 candidate input contract drifted",
        )
        _expect(
            findings,
            contract.get("candidate_or_protocol_tuning_after_first_invocation") == "invalid_experiment",
            "D2 first-observation invalidation rule drifted",
        )

    next_gate = record.get("next_gate")
    _expect(
        findings,
        isinstance(next_gate, dict)
        and next_gate.get("id") == "D2"
        and next_gate.get("state") == "blocked_pending_blind_executor_preflight",
        "D2 must remain blocked pending blind executor preflight",
    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-freeze-ready", action="store_true")
    args = parser.parse_args()

    record = _load_json(GATE_D1_PATH)
    findings = validate_gate_d1(record)
    if args.require_freeze_ready and record.get("freeze_status") != "frozen":
        findings.append("Gate D1 is not frozen")
    if findings:
        raise SystemExit("Gate D1 validation failed:\n" + "\n".join(findings))
    print("Gate D1 frozen evidence validation passed")
    print(f"materialization_main_sha={record['materialization_main_sha']}")
    print(f"artifact_sha256={record['authoritative_artifact']['sha256']}")
    print(f"input_manifest_digest={record['candidate_visible_bundle']['input_manifest_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
