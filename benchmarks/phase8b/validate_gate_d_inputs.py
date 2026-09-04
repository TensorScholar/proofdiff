from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmarks.phase8b.harness import (
    assert_candidate_payload_no_leakage,
    candidate_case_envelope,
    is_candidate_source_path,
)
from benchmarks.phase8b.materialize_gate_d_inputs import (
    BUNDLE_FORMAT,
    DIFF_POLICY,
    DIRECTIONS,
    HARNESS_PATH,
    MANIFEST_NAME,
    MATERIALIZER_PATH,
    PAYLOAD_KEYS,
    SOURCE_POLICY,
    _payload_relpath,
)

ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "benchmarks" / "phase8b"
CORPUS_PATH = PHASE / "corpus.json"
GATE_D_PATH = PHASE / "gate_d.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _evaluation_case(case: dict[str, Any]) -> bool:
    return (case.get("arm") == "historical" and case.get("eligibility") == "qualified") or (
        case.get("arm") == "control" and case.get("eligibility") == "control"
    )


def _expect(findings: list[str], condition: bool, message: str) -> None:
    if not condition:
        findings.append(message)


def _payload_bundle_findings(manifest: dict[str, Any], bundle_dir: Path) -> list[str]:
    findings: list[str] = []
    rows = manifest.get("rows")
    if not isinstance(rows, list):
        return ["cannot validate payload bundle without manifest rows"]

    expected_files = {MANIFEST_NAME}
    reconstructed_index: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        run_key = str(row.get("run_key"))
        direction = str(row.get("direction"))
        try:
            expected_relpath = _payload_relpath(run_key, direction)
        except ValueError as exc:
            findings.append(f"rows[{index}] invalid payload identity: {exc}")
            continue
        relpath = row.get("payload_relpath")
        if relpath != expected_relpath:
            findings.append(f"{run_key}:{direction}: payload path mismatch")
            continue
        expected_files.add(expected_relpath)
        payload_path = bundle_dir / expected_relpath
        if payload_path.is_symlink():
            findings.append(f"payload must not be a symlink: {expected_relpath}")
            continue
        if not payload_path.is_file():
            findings.append(f"payload file missing: {expected_relpath}")
            continue
        data = payload_path.read_bytes()
        digest = _sha256(data)
        reconstructed_index.append({"path": expected_relpath, "sha256": digest, "bytes": len(data)})
        _expect(
            findings,
            row.get("candidate_payload_digest") == digest,
            f"{run_key}:{direction}: payload digest mismatch",
        )
        _expect(
            findings,
            row.get("candidate_payload_bytes") == len(data),
            f"{run_key}:{direction}: payload byte count mismatch",
        )
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            findings.append(f"{run_key}:{direction}: invalid payload JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            findings.append(f"{run_key}:{direction}: payload must be a JSON object")
            continue
        _expect(
            findings,
            data == _canonical_bytes(payload),
            f"{run_key}:{direction}: payload bytes are not canonical JSON",
        )
        _expect(
            findings,
            set(payload) == PAYLOAD_KEYS,
            f"{run_key}:{direction}: payload key set drifted",
        )
        try:
            assert_candidate_payload_no_leakage(payload)
        except ValueError as exc:
            findings.append(f"{run_key}:{direction}: payload leakage: {exc}")

        _expect(findings, payload.get("repo") == row.get("repo"), f"{run_key}:{direction}: payload repo mismatch")
        _expect(
            findings,
            payload.get("base_sha") == row.get("baseline_sha"),
            f"{run_key}:{direction}: payload baseline SHA mismatch",
        )
        _expect(
            findings,
            payload.get("head_sha") == row.get("candidate_sha"),
            f"{run_key}:{direction}: payload candidate SHA mismatch",
        )
        _expect(
            findings,
            payload.get("method_config") == {"calibration_freshness": manifest.get("calibration_freshness")},
            f"{run_key}:{direction}: payload calibration state mismatch",
        )
        _expect(
            findings,
            row.get("baseline_source", {}).get("snapshot_digest")
            == _sha256_json(payload.get("sanitized_baseline_source")),
            f"{run_key}:{direction}: baseline source digest mismatch",
        )
        _expect(
            findings,
            row.get("candidate_source", {}).get("snapshot_digest")
            == _sha256_json(payload.get("sanitized_candidate_source")),
            f"{run_key}:{direction}: candidate source digest mismatch",
        )
        production_diff = payload.get("production_diff")
        _expect(
            findings,
            isinstance(production_diff, str)
            and row.get("production_diff_digest") == _sha256(production_diff.encode("utf-8")),
            f"{run_key}:{direction}: production diff digest mismatch",
        )
        behavior_catalog = payload.get("behavior_catalog")
        _expect(
            findings,
            row.get("behavior_catalog_digest") == _sha256_json(behavior_catalog),
            f"{run_key}:{direction}: behavior catalog digest mismatch",
        )

    actual_files: set[str] = set()
    if not bundle_dir.is_dir():
        findings.append(f"bundle directory missing: {bundle_dir}")
    else:
        for path in bundle_dir.rglob("*"):
            relpath = path.relative_to(bundle_dir).as_posix()
            if path.is_symlink():
                findings.append(f"bundle must not contain symlinks: {relpath}")
            elif path.is_file():
                actual_files.add(relpath)
    _expect(
        findings,
        actual_files == expected_files,
        f"bundle closed-set mismatch: expected {sorted(expected_files)}, got {sorted(actual_files)}",
    )

    canonical_index = sorted(reconstructed_index, key=lambda item: str(item["path"]))
    _expect(
        findings,
        manifest.get("payload_file_count") == len(canonical_index),
        "payload file count mismatch",
    )
    _expect(
        findings,
        manifest.get("payload_file_index") == canonical_index,
        "payload file index mismatch",
    )
    _expect(
        findings,
        manifest.get("candidate_payload_bundle_digest") == _sha256_json(canonical_index),
        "candidate payload bundle digest mismatch",
    )
    return findings


def validate_manifest(manifest: dict[str, Any], *, bundle_dir: Path | None = None) -> list[str]:
    findings: list[str] = []
    corpus = _load_json(CORPUS_PATH)
    gate_d = _load_json(GATE_D_PATH)

    _expect(findings, manifest.get("schema_version") == "1.1", "schema_version must be 1.1")
    _expect(findings, manifest.get("phase") == "8B", "phase must be 8B")
    _expect(findings, manifest.get("gate") == "D", "gate must be D")
    _expect(findings, manifest.get("subgate") == "D1", "subgate must be D1")
    _expect(findings, manifest.get("materialization_status") == "materialized", "D1 must be fully materialized")
    _expect(findings, manifest.get("materialization_failures") == [], "D1 manifest contains materialization failures")
    _expect(
        findings, manifest.get("candidate_execution_permitted") is False, "candidate execution must remain forbidden"
    )
    _expect(
        findings,
        manifest.get("candidate_imported_during_materialization") is False,
        "candidate module must not be imported during D1",
    )

    execution = gate_d.get("execution_design", {})
    _expect(
        findings,
        manifest.get("calibration_freshness")
        == execution.get("candidate_calibration_freshness")
        == "not_yet_calibrated",
        "D1 must preserve the frozen cold-start calibration state",
    )
    _expect(findings, manifest.get("source_snapshot_policy") == SOURCE_POLICY, "source snapshot policy drifted")
    _expect(findings, manifest.get("production_diff_policy") == DIFF_POLICY, "production diff policy drifted")
    _expect(findings, manifest.get("bundle_format") == BUNDLE_FORMAT, "payload bundle format drifted")
    _expect(
        findings, manifest.get("candidate_payload_keys") == sorted(PAYLOAD_KEYS), "candidate payload key set drifted"
    )
    _expect(
        findings,
        manifest.get("candidate_payload_keys") == sorted(execution.get("candidate_visible_fields", [])),
        "D1 candidate payload keys must exactly match frozen Gate D visibility",
    )

    _expect(findings, manifest.get("protocol_blob_sha") == _git_blob_sha(GATE_D_PATH), "protocol blob mismatch")
    _expect(findings, manifest.get("corpus_blob_sha") == _git_blob_sha(CORPUS_PATH), "corpus blob mismatch")
    _expect(findings, manifest.get("harness_blob_sha") == _git_blob_sha(HARNESS_PATH), "harness blob mismatch")
    _expect(
        findings,
        manifest.get("materializer_blob_sha") == _git_blob_sha(MATERIALIZER_PATH),
        "materializer blob mismatch",
    )
    _expect(
        findings,
        manifest.get("candidate_blob_sha") == gate_d.get("frozen_inputs", {}).get("candidate", {}).get("git_blob_sha"),
        "candidate blob mismatch",
    )
    _expect(
        findings,
        manifest.get("candidate_id") == gate_d.get("frozen_inputs", {}).get("candidate", {}).get("id"),
        "candidate id mismatch",
    )

    expected_cases = {
        str(case["case_id"]): case
        for case in corpus.get("cases", [])
        if isinstance(case, dict) and _evaluation_case(case)
    }
    _expect(findings, manifest.get("evaluation_case_count") == len(expected_cases), "evaluation case count mismatch")

    rows = manifest.get("rows")
    if not isinstance(rows, list):
        return [*findings, "rows must be a list"]
    _expect(findings, manifest.get("case_direction_count") == len(rows), "case-direction count mismatch")
    _expect(
        findings, len(rows) == len(expected_cases) * len(DIRECTIONS), "each evaluation case must have both directions"
    )

    seen: set[tuple[str, str]] = set()
    by_case: dict[str, set[str]] = defaultdict(set)
    payload_set: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            findings.append(f"rows[{index}] must be an object")
            continue
        case_id = str(row.get("case_id"))
        direction = str(row.get("direction"))
        case = expected_cases.get(case_id)
        if case is None:
            findings.append(f"rows[{index}] references unknown evaluation case: {case_id}")
            continue
        if direction not in DIRECTIONS:
            findings.append(f"rows[{index}] has unsupported direction: {direction}")
            continue
        key = (case_id, direction)
        if key in seen:
            findings.append(f"duplicate case-direction row: {case_id}:{direction}")
            continue
        seen.add(key)
        by_case[case_id].add(direction)

        frozen_base = str(case["base_sha"])
        frozen_head = str(case["head_sha"])
        expected_baseline, expected_candidate = (
            (frozen_base, frozen_head) if direction == "forward" else (frozen_head, frozen_base)
        )
        expected_run_key = candidate_case_envelope(case)["run_key"]
        _expect(findings, row.get("repo") == case.get("repo"), f"{case_id}:{direction}: repo mismatch")
        _expect(
            findings,
            row.get("run_key") == expected_run_key,
            f"{case_id}:{direction}: run_key mismatch",
        )
        _expect(
            findings,
            row.get("payload_relpath") == _payload_relpath(expected_run_key, direction),
            f"{case_id}:{direction}: payload relpath mismatch",
        )
        _expect(findings, row.get("arm") == case.get("arm"), f"{case_id}:{direction}: arm mismatch")
        _expect(
            findings, row.get("eligibility") == case.get("eligibility"), f"{case_id}:{direction}: eligibility mismatch"
        )
        _expect(findings, row.get("family_id") == case.get("family_id"), f"{case_id}:{direction}: family mismatch")
        _expect(findings, row.get("baseline_sha") == expected_baseline, f"{case_id}:{direction}: baseline SHA mismatch")
        _expect(
            findings, row.get("candidate_sha") == expected_candidate, f"{case_id}:{direction}: candidate SHA mismatch"
        )
        _expect(
            findings,
            row.get("candidate_payload_top_level_keys") == sorted(PAYLOAD_KEYS),
            f"{case_id}:{direction}: candidate payload keys drifted",
        )
        _expect(findings, row.get("leakage_assertion") == "passed", f"{case_id}:{direction}: leakage assertion failed")

        changed_paths = row.get("changed_paths")
        if not isinstance(changed_paths, list):
            findings.append(f"{case_id}:{direction}: changed_paths must be a list")
        else:
            _expect(
                findings,
                changed_paths == sorted(set(changed_paths)),
                f"{case_id}:{direction}: changed paths not canonical",
            )
            for path in changed_paths:
                _expect(
                    findings,
                    isinstance(path, str) and is_candidate_source_path(path),
                    f"{case_id}:{direction}: unsanitized changed path: {path!r}",
                )

        for field in ("behavior_catalog_digest", "production_diff_digest", "candidate_payload_digest"):
            _expect(
                findings,
                isinstance(row.get(field), str) and bool(HEX64.fullmatch(str(row.get(field)))),
                f"{case_id}:{direction}: invalid {field}",
            )
        _expect(
            findings,
            isinstance(row.get("candidate_payload_bytes"), int) and row.get("candidate_payload_bytes", -1) >= 0,
            f"{case_id}:{direction}: invalid candidate payload byte count",
        )
        for source_field in ("baseline_source", "candidate_source"):
            source = row.get(source_field)
            if not isinstance(source, dict):
                findings.append(f"{case_id}:{direction}: {source_field} must be an object")
                continue
            _expect(
                findings,
                isinstance(source.get("snapshot_digest"), str)
                and bool(HEX64.fullmatch(str(source.get("snapshot_digest")))),
                f"{case_id}:{direction}: invalid {source_field} digest",
            )
            _expect(
                findings,
                isinstance(source.get("file_count"), int) and source.get("file_count", -1) >= 0,
                f"{case_id}:{direction}: invalid {source_field} file count",
            )
            nonregular = source.get("nonregular_python_paths")
            _expect(
                findings,
                isinstance(nonregular, list) and nonregular == sorted(set(nonregular)),
                f"{case_id}:{direction}: nonregular path evidence must be canonical",
            )

        payload_digest = str(row.get("candidate_payload_digest"))
        payload_set.append({"run_key": row.get("run_key"), "direction": direction, "payload_digest": payload_digest})

    for case_id in sorted(expected_cases):
        _expect(findings, by_case.get(case_id) == set(DIRECTIONS), f"{case_id}: missing direction")

    canonical_payload_set = sorted(payload_set, key=lambda item: (str(item["run_key"]), str(item["direction"])))
    _expect(
        findings,
        manifest.get("candidate_visible_payload_set_digest") == _sha256_json(canonical_payload_set),
        "candidate-visible payload-set digest mismatch",
    )

    manifest_digest = manifest.get("input_manifest_digest")
    core = dict(manifest)
    core.pop("input_manifest_digest", None)
    _expect(
        findings,
        isinstance(manifest_digest, str)
        and bool(HEX64.fullmatch(manifest_digest))
        and manifest_digest == _sha256_json(core),
        "input manifest digest mismatch",
    )
    if bundle_dir is not None:
        findings.extend(_payload_bundle_findings(manifest, bundle_dir))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    manifest_path = args.bundle_dir / MANIFEST_NAME
    manifest = _load_json(manifest_path)
    findings = validate_manifest(manifest, bundle_dir=args.bundle_dir)
    if findings:
        raise SystemExit("Gate D1 input bundle validation failed:\n" + "\n".join(findings))
    print("Gate D1 input bundle validation passed")
    print(f"payload_bundle_digest={manifest['candidate_payload_bundle_digest']}")
    print(f"input_manifest_digest={manifest['input_manifest_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
