from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from benchmarks.phase8b.harness import (
    assert_candidate_payload_no_leakage,
    candidate_case_envelope,
    derive_behavior_catalog,
    is_candidate_source_path,
)
from benchmarks.phase8b.materialize_gate_d_inputs import CANDIDATE_VISIBLE_FIELDS, canonical_sha256

ROOT = Path(__file__).parents[2]
PHASE = ROOT / "benchmarks" / "phase8b"
CORPUS_PATH = PHASE / "corpus.json"
GATE_D_PATH = PHASE / "gate_d.json"
STATIC_RULES_PATH = PHASE / "static_rules.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _eligible_case(case: dict[str, Any]) -> bool:
    return (case.get("arm") == "historical" and case.get("eligibility") == "qualified") or (
        case.get("arm") == "control" and case.get("eligibility") == "control"
    )


def _expect(findings: list[str], condition: bool, message: str) -> None:
    if not condition:
        findings.append(message)


def _artifact_path(root: Path, ref: Any, findings: list[str], *, label: str) -> Path | None:
    if not isinstance(ref, str) or not ref:
        findings.append(f"{label} must be a non-empty relative artifact path")
        return None
    pure = PurePosixPath(ref)
    if pure.is_absolute() or ".." in pure.parts:
        findings.append(f"{label} must not escape the artifact root: {ref}")
        return None
    candidate = root.joinpath(*pure.parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        findings.append(f"{label} resolves outside the artifact root: {ref}")
        return None
    if not candidate.is_file():
        findings.append(f"{label} is missing: {ref}")
        return None
    return candidate


def _locked_blobs(gate_d: dict[str, Any]) -> dict[str, str]:
    frozen = gate_d["frozen_inputs"]
    return {
        "protocol_blob_sha": _git_blob_sha(GATE_D_PATH),
        "corpus_blob_sha": str(frozen["corpus"]["git_blob_sha"]),
        "gate_b_blob_sha": str(frozen["gate_b"]["git_blob_sha"]),
        "static_rules_blob_sha": str(frozen["static_rules"]["git_blob_sha"]),
        "harness_blob_sha": str(frozen["harness"]["git_blob_sha"]),
        "methods_blob_sha": str(frozen["methods"]["git_blob_sha"]),
        "candidate_blob_sha": str(frozen["candidate"]["git_blob_sha"]),
    }


def _validate_snapshot(
    snapshot: Any,
    *,
    repo: str,
    sha: str,
    findings: list[str],
    label: str,
) -> dict[str, str]:
    if not isinstance(snapshot, dict):
        findings.append(f"{label} must be a JSON object")
        return {}
    _expect(findings, snapshot.get("schema_version") == "1.0", f"{label}.schema_version must be 1.0")
    _expect(findings, snapshot.get("repo") == repo, f"{label}.repo mismatch")
    _expect(findings, snapshot.get("sha") == sha, f"{label}.sha mismatch")
    _expect(
        findings,
        snapshot.get("source_projection") == "frozen_candidate_path_filter_and_locked_candidate_python_suffix",
        f"{label}.source_projection drifted",
    )
    sources = snapshot.get("sources")
    if not isinstance(sources, dict):
        findings.append(f"{label}.sources must be an object")
        return {}
    typed_sources: dict[str, str] = {}
    for path, text in sources.items():
        if not isinstance(path, str) or not isinstance(text, str):
            findings.append(f"{label}.sources must map string paths to string source")
            continue
        if not is_candidate_source_path(path) or not path.endswith(".py"):
            findings.append(f"{label} contains source outside the frozen projection: {path}")
        typed_sources[path] = text
    _expect(findings, list(typed_sources) == sorted(typed_sources), f"{label}.sources must be path-sorted")
    _expect(findings, snapshot.get("source_count") == len(typed_sources), f"{label}.source_count mismatch")
    _expect(
        findings,
        snapshot.get("source_digest") == canonical_sha256(typed_sources),
        f"{label}.source_digest mismatch",
    )
    _expect(findings, bool(typed_sources), f"{label} must contain candidate-relevant Python source")
    return typed_sources


def _validate_production_diff(value: Any, *, findings: list[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        findings.append(f"{label} must be an object")
        return {"changed_paths": [], "unified_diff": ""}
    paths = value.get("changed_paths")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        findings.append(f"{label}.changed_paths must be a string list")
        paths = []
    typed_paths = [str(path) for path in paths]
    _expect(findings, bool(typed_paths), f"{label}.changed_paths must not be empty")
    _expect(findings, typed_paths == sorted(set(typed_paths)), f"{label}.changed_paths must be sorted and unique")
    for path in typed_paths:
        _expect(
            findings,
            is_candidate_source_path(path),
            f"{label}.changed_paths contains excluded surface: {path}",
        )
    _expect(
        findings,
        value.get("rename_policy") == "disabled_decompose_to_delete_add",
        f"{label}.rename_policy drifted",
    )
    unified_diff = value.get("unified_diff")
    if not isinstance(unified_diff, str):
        findings.append(f"{label}.unified_diff must be a string")
        unified_diff = ""
    _expect(findings, bool(unified_diff), f"{label}.unified_diff must not be empty")
    _expect(
        findings,
        value.get("unified_diff_sha256") == hashlib.sha256(unified_diff.encode("utf-8")).hexdigest(),
        f"{label}.unified_diff_sha256 mismatch",
    )
    return {
        "changed_paths": typed_paths,
        "rename_policy": value.get("rename_policy"),
        "unified_diff": unified_diff,
        "unified_diff_sha256": value.get("unified_diff_sha256"),
    }


def validate_materialization(root: Path) -> list[str]:
    findings: list[str] = []
    manifest_path = root / "gate_d_input_manifest.json"
    if not manifest_path.is_file():
        return ["gate_d_input_manifest.json is missing"]
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        return ["Gate D1 manifest must be a JSON object"]

    corpus = _load_json(CORPUS_PATH)
    gate_d = _load_json(GATE_D_PATH)
    rules = _load_json(STATIC_RULES_PATH)
    if not isinstance(corpus, dict) or not isinstance(gate_d, dict) or not isinstance(rules, dict):
        return ["frozen Phase 8B inputs must be JSON objects"]

    _expect(findings, gate_d.get("protocol_status") == "frozen", "Gate D protocol must remain frozen")
    _expect(findings, manifest.get("schema_version") == "1.0", "manifest.schema_version must be 1.0")
    _expect(findings, manifest.get("phase") == "8B", "manifest.phase must be 8B")
    _expect(findings, manifest.get("gate") == "D1", "manifest.gate must be D1")
    _expect(findings, manifest.get("materialization_status") == "complete", "materialization must be complete")
    _expect(findings, manifest.get("candidate_execution_count") == 0, "D1 candidate execution count must be zero")
    _expect(
        findings,
        manifest.get("candidate_execution_attestation")
        == "minimal_big_v1 was not imported or invoked during materialization",
        "D1 candidate execution attestation drifted",
    )
    _expect(findings, manifest.get("network_role") == "evaluator_only", "D1 network role must be evaluator-only")
    _expect(
        findings,
        manifest.get("fetch_policy") == "github_repo_exact_frozen_sha_only",
        "D1 fetch policy drifted",
    )
    _expect(
        findings,
        manifest.get("rename_policy") == "disabled_decompose_to_delete_add",
        "D1 rename policy drifted",
    )
    _expect(
        findings,
        manifest.get("source_projection") == "frozen_candidate_path_filter_and_locked_candidate_python_suffix",
        "D1 source projection drifted",
    )
    _expect(findings, manifest.get("locked_blobs") == _locked_blobs(gate_d), "D1 locked blob inventory mismatch")
    _expect(
        findings,
        manifest.get("candidate_visible_fields") == sorted(CANDIDATE_VISIBLE_FIELDS),
        "D1 candidate-visible field set drifted",
    )

    stored_manifest_digest = manifest.get("input_manifest_digest")
    manifest_core = dict(manifest)
    manifest_core.pop("input_manifest_digest", None)
    _expect(
        findings,
        stored_manifest_digest == canonical_sha256(manifest_core),
        "D1 input_manifest_digest mismatch",
    )

    raw_cases = corpus.get("cases", [])
    cases = [case for case in raw_cases if isinstance(case, dict) and _eligible_case(case)]
    case_by_id = {str(case["case_id"]): case for case in cases}
    catalogs = derive_behavior_catalog(corpus)
    directions = gate_d.get("execution_design", {}).get("directions")
    _expect(findings, directions == ["forward", "reverse"], "frozen direction contract drifted")
    expected_units = {(case_id, direction) for case_id in case_by_id for direction in ("forward", "reverse")}

    _expect(findings, manifest.get("case_count") == len(cases), "D1 case_count mismatch")
    _expect(findings, manifest.get("run_count") == len(expected_units), "D1 run_count mismatch")
    _expect(findings, manifest.get("repository_count") == len({str(case["repo"]) for case in cases}), "D1 repository_count mismatch")

    raw_runs = manifest.get("runs")
    if not isinstance(raw_runs, list):
        findings.append("manifest.runs must be a list")
        raw_runs = []
    observed_units: set[tuple[str, str]] = set()
    observed_run_ids: set[str] = set()

    for index, summary in enumerate(raw_runs):
        label = f"manifest.runs[{index}]"
        if not isinstance(summary, dict):
            findings.append(f"{label} must be an object")
            continue
        case_id = str(summary.get("case_id", ""))
        direction = str(summary.get("direction", ""))
        case = case_by_id.get(case_id)
        if case is None:
            findings.append(f"{label} references unknown case_id: {case_id}")
            continue
        if direction not in {"forward", "reverse"}:
            findings.append(f"{label} has invalid direction: {direction}")
            continue
        unit = (case_id, direction)
        if unit in observed_units:
            findings.append(f"duplicate D1 case-direction unit: {case_id}/{direction}")
        observed_units.add(unit)

        repo = str(case["repo"])
        original_base = str(case["base_sha"])
        original_head = str(case["head_sha"])
        base_sha, head_sha = (
            (original_base, original_head) if direction == "forward" else (original_head, original_base)
        )
        expected_run_key = candidate_case_envelope(case)["run_key"]
        expected_run_id = f"{expected_run_key}-{direction}"
        _expect(findings, summary.get("run_id") == expected_run_id, f"{label}.run_id mismatch")
        _expect(findings, summary.get("repo") == repo, f"{label}.repo mismatch")
        _expect(findings, summary.get("base_sha") == base_sha, f"{label}.base_sha mismatch")
        _expect(findings, summary.get("head_sha") == head_sha, f"{label}.head_sha mismatch")
        if expected_run_id in observed_run_ids:
            findings.append(f"duplicate D1 run_id: {expected_run_id}")
        observed_run_ids.add(expected_run_id)

        descriptor_path = _artifact_path(root, summary.get("descriptor_ref"), findings, label=f"{label}.descriptor_ref")
        if descriptor_path is None:
            continue
        descriptor = _load_json(descriptor_path)
        if not isinstance(descriptor, dict):
            findings.append(f"{label} descriptor must be an object")
            continue
        _expect(findings, descriptor.get("run_id") == expected_run_id, f"{label} descriptor run_id mismatch")
        _expect(findings, descriptor.get("run_key") == expected_run_key, f"{label} descriptor run_key mismatch")
        _expect(findings, descriptor.get("case_id") == case["case_id"], f"{label} descriptor case_id mismatch")
        _expect(findings, descriptor.get("direction") == direction, f"{label} descriptor direction mismatch")
        _expect(findings, descriptor.get("repo") == repo, f"{label} descriptor repo mismatch")
        _expect(findings, descriptor.get("base_sha") == base_sha, f"{label} descriptor base_sha mismatch")
        _expect(findings, descriptor.get("head_sha") == head_sha, f"{label} descriptor head_sha mismatch")
        _expect(findings, descriptor.get("candidate_invoked") is False, f"{label} must attest candidate_invoked=false")
        _expect(findings, descriptor.get("leakage_check") == "passed", f"{label} leakage_check must be passed")
        _expect(
            findings,
            descriptor.get("candidate_payload_keys") == sorted(CANDIDATE_VISIBLE_FIELDS),
            f"{label} candidate_payload_keys drifted",
        )

        baseline_path = _artifact_path(
            root,
            descriptor.get("baseline_snapshot_ref"),
            findings,
            label=f"{label}.baseline_snapshot_ref",
        )
        candidate_path = _artifact_path(
            root,
            descriptor.get("candidate_snapshot_ref"),
            findings,
            label=f"{label}.candidate_snapshot_ref",
        )
        catalog_path = _artifact_path(
            root,
            descriptor.get("behavior_catalog_ref"),
            findings,
            label=f"{label}.behavior_catalog_ref",
        )
        method_config_path = _artifact_path(
            root,
            descriptor.get("method_config_ref"),
            findings,
            label=f"{label}.method_config_ref",
        )
        if None in {baseline_path, candidate_path, catalog_path, method_config_path}:
            continue
        assert baseline_path is not None
        assert candidate_path is not None
        assert catalog_path is not None
        assert method_config_path is not None

        baseline_sources = _validate_snapshot(
            _load_json(baseline_path),
            repo=repo,
            sha=base_sha,
            findings=findings,
            label=f"{label}.baseline_snapshot",
        )
        candidate_sources = _validate_snapshot(
            _load_json(candidate_path),
            repo=repo,
            sha=head_sha,
            findings=findings,
            label=f"{label}.candidate_snapshot",
        )
        behavior_catalog = _load_json(catalog_path)
        _expect(findings, behavior_catalog == catalogs.get(repo), f"{label} behavior catalog mismatch")
        method_config = _load_json(method_config_path)
        _expect(findings, method_config == rules, f"{label} method_config must equal frozen static rules")
        production_diff = _validate_production_diff(
            descriptor.get("production_diff"),
            findings=findings,
            label=f"{label}.production_diff",
        )
        payload = {
            "repo": repo,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "sanitized_baseline_source": baseline_sources,
            "sanitized_candidate_source": candidate_sources,
            "production_diff": production_diff,
            "behavior_catalog": behavior_catalog,
            "method_config": method_config,
        }
        try:
            assert_candidate_payload_no_leakage(payload)
        except ValueError as exc:
            findings.append(f"{label} candidate payload leakage: {exc}")
        payload_digest = canonical_sha256(payload)
        _expect(
            findings,
            descriptor.get("candidate_payload_digest") == payload_digest,
            f"{label} descriptor candidate_payload_digest mismatch",
        )
        _expect(
            findings,
            summary.get("candidate_payload_digest") == payload_digest,
            f"{label} manifest candidate_payload_digest mismatch",
        )
        _expect(
            findings,
            summary.get("changed_path_count") == len(production_diff["changed_paths"]),
            f"{label}.changed_path_count mismatch",
        )

    _expect(findings, observed_units == expected_units, "D1 case-direction coverage is incomplete or contains extras")

    raw_inventory = manifest.get("snapshot_inventory")
    if not isinstance(raw_inventory, list):
        findings.append("manifest.snapshot_inventory must be a list")
        raw_inventory = []
    expected_snapshots = {(str(case["repo"]), str(sha)) for case in cases for sha in (case["base_sha"], case["head_sha"])}
    observed_snapshots: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_inventory):
        label = f"manifest.snapshot_inventory[{index}]"
        if not isinstance(item, dict):
            findings.append(f"{label} must be an object")
            continue
        repo = str(item.get("repo", ""))
        sha = str(item.get("sha", ""))
        observed_snapshots.add((repo, sha))
        snapshot_path = _artifact_path(root, item.get("snapshot_ref"), findings, label=f"{label}.snapshot_ref")
        if snapshot_path is None:
            continue
        sources = _validate_snapshot(
            _load_json(snapshot_path),
            repo=repo,
            sha=sha,
            findings=findings,
            label=label,
        )
        _expect(findings, item.get("source_count") == len(sources), f"{label}.source_count mismatch")
        _expect(findings, item.get("source_digest") == canonical_sha256(sources), f"{label}.source_digest mismatch")
    _expect(findings, observed_snapshots == expected_snapshots, "D1 snapshot inventory mismatch")
    _expect(findings, manifest.get("snapshot_count") == len(expected_snapshots), "D1 snapshot_count mismatch")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    findings = validate_materialization(args.root.resolve())
    if findings:
        raise SystemExit("Gate D1 materialization validation failed:\n" + "\n".join(findings))
    print("Gate D1 materialization validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
