from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmarks.phase8b.harness import candidate_case_envelope, is_candidate_source_path
from benchmarks.phase8b.materialize_gate_d_inputs import DIFF_POLICY, DIRECTIONS, PAYLOAD_KEYS, SOURCE_POLICY

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


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


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


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    corpus = _load_json(CORPUS_PATH)
    gate_d = _load_json(GATE_D_PATH)

    _expect(findings, manifest.get("schema_version") == "1.0", "schema_version must be 1.0")
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
        _expect(findings, row.get("repo") == case.get("repo"), f"{case_id}:{direction}: repo mismatch")
        _expect(
            findings,
            row.get("run_key") == candidate_case_envelope(case)["run_key"],
            f"{case_id}:{direction}: run_key mismatch",
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
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = _load_json(args.manifest)
    findings = validate_manifest(manifest)
    if findings:
        raise SystemExit("Gate D1 input manifest validation failed:\n" + "\n".join(findings))
    print("Gate D1 input manifest validation passed")
    print(f"input_manifest_digest={manifest['input_manifest_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
