from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from benchmarks.phase8b import materialize_gate_d_inputs as d1
from benchmarks.phase8b import validate_gate_d_inputs as d1v


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _fixture_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "ProofDiff Test")
    _git(repo, "config", "user.email", "proofdiff@example.invalid")

    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "core.py").write_text("def route_request():\n    return 'base'\n", encoding="utf-8")
    (repo / "src" / "delete_me.py").write_text("def old_path():\n    return True\n", encoding="utf-8")
    (repo / "tests" / "test_core.py").write_text("def test_base():\n    assert True\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("base docs\n", encoding="utf-8")
    (repo / "config.yaml").write_text("provider: alpha\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    (repo / "src" / "core.py").write_text("def route_request():\n    return 'candidate'\n", encoding="utf-8")
    (repo / "src" / "delete_me.py").unlink()
    (repo / "src" / "new.py").write_text("def new_route():\n    return True\n", encoding="utf-8")
    (repo / "tests" / "test_core.py").write_text("def test_candidate():\n    assert True\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("candidate docs\n", encoding="utf-8")
    (repo / "config.yaml").write_text("provider: beta\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "candidate")
    head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head


def test_d1_snapshot_and_diff_preserve_uncertainty_without_oracle_surfaces(tmp_path: Path) -> None:
    repo, base, head = _fixture_repo(tmp_path)
    baseline, _ = d1._source_snapshot(repo, base)
    candidate, _ = d1._source_snapshot(repo, head)
    changed = d1._changed_paths(repo, base, head)
    diff = d1._production_diff(repo, base, head, changed)

    assert sorted(baseline) == ["src/core.py", "src/delete_me.py"]
    assert sorted(candidate) == ["src/core.py", "src/new.py"]
    assert changed == ["config.yaml", "src/core.py", "src/delete_me.py", "src/new.py"]
    assert "tests/test_core.py" not in diff
    assert "docs/guide.md" not in diff
    assert "config.yaml" in diff
    assert "src/delete_me.py" in diff


def test_forward_and_reverse_payloads_are_directionally_distinct_and_deterministic(tmp_path: Path) -> None:
    repo, base, head = _fixture_repo(tmp_path)
    base_sources, _ = d1._source_snapshot(repo, base)
    head_sources, _ = d1._source_snapshot(repo, head)
    changed = d1._changed_paths(repo, base, head)

    forward = d1._payload(
        repo="owner/repo",
        baseline_sha=base,
        candidate_sha=head,
        baseline_sources=base_sources,
        candidate_sources=head_sources,
        production_diff=d1._production_diff(repo, base, head, changed),
        behavior_catalog=[],
        calibration_freshness="not_yet_calibrated",
    )
    reverse = d1._payload(
        repo="owner/repo",
        baseline_sha=head,
        candidate_sha=base,
        baseline_sources=head_sources,
        candidate_sources=base_sources,
        production_diff=d1._production_diff(repo, head, base, changed),
        behavior_catalog=[],
        calibration_freshness="not_yet_calibrated",
    )
    assert d1._sha256_json(forward) == d1._sha256_json(copy.deepcopy(forward))
    assert d1._sha256_json(forward) != d1._sha256_json(reverse)
    assert forward["base_sha"] == reverse["head_sha"]
    assert forward["head_sha"] == reverse["base_sha"]


def test_materializer_has_no_big_import_or_candidate_invocation_and_no_lazy_blob_fetch() -> None:
    source = d1.MATERIALIZER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all("big_candidate" not in name for name in imported)
    assert "select_with_big" not in source
    assert "--filter=blob:none" not in source
    assert d1.FETCH_TIMEOUT_SECONDS > 0


def _canonical_payload(*, repo: str, baseline_sha: str, candidate_sha: str) -> dict[str, Any]:
    return {
        "repo": repo,
        "base_sha": baseline_sha,
        "head_sha": candidate_sha,
        "sanitized_baseline_source": {},
        "sanitized_candidate_source": {},
        "production_diff": "",
        "behavior_catalog": [],
        "method_config": {"calibration_freshness": "not_yet_calibrated"},
    }


def _write_manifest(bundle_dir: Path, manifest: dict[str, Any]) -> None:
    (bundle_dir / d1.MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rehash_manifest(manifest: dict[str, Any]) -> None:
    rows = manifest["rows"]
    manifest["payload_file_index"] = [
        {
            "path": row["payload_relpath"],
            "sha256": row["candidate_payload_digest"],
            "bytes": row["candidate_payload_bytes"],
        }
        for row in rows
    ]
    manifest["payload_file_count"] = len(manifest["payload_file_index"])
    manifest["candidate_payload_bundle_digest"] = d1v._sha256_json(manifest["payload_file_index"])
    payload_set = [
        {
            "run_key": row["run_key"],
            "direction": row["direction"],
            "payload_digest": row["candidate_payload_digest"],
        }
        for row in rows
    ]
    manifest["candidate_visible_payload_set_digest"] = d1v._sha256_json(payload_set)
    manifest.pop("input_manifest_digest", None)
    manifest["input_manifest_digest"] = d1v._sha256_json(manifest)


def _synthetic_valid_bundle(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    corpus = json.loads(d1.CORPUS_PATH.read_text(encoding="utf-8"))
    gate_d = json.loads(d1.GATE_D_PATH.read_text(encoding="utf-8"))
    cases = [case for case in corpus["cases"] if d1._evaluation_case(case)]
    bundle_dir = tmp_path / "bundle"
    (bundle_dir / d1.PAYLOAD_DIR_NAME).mkdir(parents=True)

    rows: list[dict[str, Any]] = []
    empty_digest = d1v._sha256_json({})
    catalog_digest = d1v._sha256_json([])
    diff_digest = d1v._sha256(b"")
    for case in sorted(cases, key=lambda item: item["case_id"]):
        run_key = d1.candidate_case_envelope(case)["run_key"]
        for direction in d1.DIRECTIONS:
            baseline, candidate = (
                (case["base_sha"], case["head_sha"]) if direction == "forward" else (case["head_sha"], case["base_sha"])
            )
            payload = _canonical_payload(repo=case["repo"], baseline_sha=baseline, candidate_sha=candidate)
            payload_bytes = d1._canonical_bytes(payload)
            relpath = d1._payload_relpath(run_key, direction)
            (bundle_dir / relpath).write_bytes(payload_bytes)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "arm": case["arm"],
                    "eligibility": case["eligibility"],
                    "family_id": case["family_id"],
                    "run_key": run_key,
                    "direction": direction,
                    "repo": case["repo"],
                    "baseline_sha": baseline,
                    "candidate_sha": candidate,
                    "changed_paths": [],
                    "behavior_catalog_digest": catalog_digest,
                    "baseline_source": {
                        "file_count": 0,
                        "nonregular_python_paths": [],
                        "snapshot_digest": empty_digest,
                    },
                    "candidate_source": {
                        "file_count": 0,
                        "nonregular_python_paths": [],
                        "snapshot_digest": empty_digest,
                    },
                    "production_diff_digest": diff_digest,
                    "production_diff_bytes": 0,
                    "candidate_payload_top_level_keys": sorted(d1.PAYLOAD_KEYS),
                    "payload_relpath": relpath,
                    "candidate_payload_digest": d1v._sha256(payload_bytes),
                    "candidate_payload_bytes": len(payload_bytes),
                    "leakage_assertion": "passed",
                }
            )
    rows.sort(key=lambda row: (str(row["run_key"]), str(row["direction"])))

    manifest: dict[str, Any] = {
        "schema_version": "1.1",
        "phase": "8B",
        "gate": "D",
        "subgate": "D1",
        "materialization_status": "materialized",
        "protocol_blob_sha": d1v._git_blob_sha(d1.GATE_D_PATH),
        "corpus_blob_sha": d1v._git_blob_sha(d1.CORPUS_PATH),
        "materializer_blob_sha": d1._git_blob_sha(d1.MATERIALIZER_PATH),
        "candidate_id": gate_d["frozen_inputs"]["candidate"]["id"],
        "candidate_blob_sha": gate_d["frozen_inputs"]["candidate"]["git_blob_sha"],
        "calibration_freshness": "not_yet_calibrated",
        "source_snapshot_policy": d1.SOURCE_POLICY,
        "production_diff_policy": d1.DIFF_POLICY,
        "bundle_format": d1.BUNDLE_FORMAT,
        "candidate_payload_keys": sorted(d1.PAYLOAD_KEYS),
        "candidate_imported_during_materialization": False,
        "candidate_execution_permitted": False,
        "evaluation_case_count": len(cases),
        "case_direction_count": len(rows),
        "rows": rows,
        "materialization_failures": [],
    }
    _rehash_manifest(manifest)
    _write_manifest(bundle_dir, manifest)
    return manifest, bundle_dir


def test_bundle_validator_accepts_exact_closed_set(tmp_path: Path) -> None:
    manifest, bundle_dir = _synthetic_valid_bundle(tmp_path)
    assert d1v.validate_manifest(manifest, bundle_dir=bundle_dir) == []


def test_bundle_validator_rejects_missing_unexpected_and_symlink_files(tmp_path: Path) -> None:
    manifest, bundle_dir = _synthetic_valid_bundle(tmp_path)
    first_payload = bundle_dir / manifest["rows"][0]["payload_relpath"]
    first_payload.unlink()
    findings = d1v.validate_manifest(manifest, bundle_dir=bundle_dir)
    assert any("payload file missing" in item or "closed-set mismatch" in item for item in findings)

    manifest, bundle_dir = _synthetic_valid_bundle(tmp_path / "unexpected")
    (bundle_dir / "unexpected.txt").write_text("not allowed", encoding="utf-8")
    assert any("closed-set mismatch" in item for item in d1v.validate_manifest(manifest, bundle_dir=bundle_dir))

    manifest, bundle_dir = _synthetic_valid_bundle(tmp_path / "symlink")
    link = bundle_dir / "payloads" / "extra-link"
    os.symlink(manifest["rows"][0]["payload_relpath"], link)
    assert any("symlink" in item for item in d1v.validate_manifest(manifest, bundle_dir=bundle_dir))


def test_bundle_validator_rejects_byte_tampering_and_noncanonical_json(tmp_path: Path) -> None:
    manifest, bundle_dir = _synthetic_valid_bundle(tmp_path)
    payload_path = bundle_dir / manifest["rows"][0]["payload_relpath"]
    payload_path.write_bytes(payload_path.read_bytes() + b"\n")
    findings = d1v.validate_manifest(manifest, bundle_dir=bundle_dir)
    assert any("payload digest mismatch" in item for item in findings)
    assert any("not canonical JSON" in item for item in findings)


def test_bundle_validator_rejects_payload_leakage_even_with_rehashed_metadata(tmp_path: Path) -> None:
    manifest, bundle_dir = _synthetic_valid_bundle(tmp_path)
    row = manifest["rows"][0]
    payload_path = bundle_dir / row["payload_relpath"]
    payload = json.loads(payload_path.read_bytes())
    payload["case_id"] = "oracle-leak"
    payload_bytes = d1._canonical_bytes(payload)
    payload_path.write_bytes(payload_bytes)
    row["candidate_payload_digest"] = d1v._sha256(payload_bytes)
    row["candidate_payload_bytes"] = len(payload_bytes)
    _rehash_manifest(manifest)
    _write_manifest(bundle_dir, manifest)

    findings = d1v.validate_manifest(manifest, bundle_dir=bundle_dir)
    assert any("payload leakage" in item for item in findings)
    assert any("payload key set drifted" in item for item in findings)


def test_manifest_validator_rejects_posthoc_identity_and_calibration_drift(tmp_path: Path) -> None:
    valid, bundle_dir = _synthetic_valid_bundle(tmp_path)

    stale_materializer = copy.deepcopy(valid)
    stale_materializer["materializer_blob_sha"] = "0" * 40
    assert any(
        "materializer blob mismatch" in item
        for item in d1v.validate_manifest(stale_materializer, bundle_dir=bundle_dir)
    )

    imported = copy.deepcopy(valid)
    imported["candidate_imported_during_materialization"] = True
    assert any("must not be imported" in item for item in d1v.validate_manifest(imported, bundle_dir=bundle_dir))

    calibrated = copy.deepcopy(valid)
    calibrated["calibration_freshness"] = "fresh"
    assert any("cold-start" in item for item in d1v.validate_manifest(calibrated, bundle_dir=bundle_dir))

    widened_visibility = copy.deepcopy(valid)
    widened_visibility["candidate_payload_keys"] = sorted([*d1.PAYLOAD_KEYS, "case_id"])
    assert any("payload key" in item for item in d1v.validate_manifest(widened_visibility, bundle_dir=bundle_dir))
