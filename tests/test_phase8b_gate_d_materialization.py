from __future__ import annotations

import ast
import copy
import json
import subprocess
from pathlib import Path

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

    payload = d1._payload(
        repo="owner/repo",
        baseline_sha=base,
        candidate_sha=head,
        baseline_sources=baseline,
        candidate_sources=candidate,
        production_diff=diff,
        behavior_catalog=[
            {
                "behavior_id": "b_safe",
                "repo": "owner/repo",
                "description": "route request",
                "surface_tags": ["routing"],
                "risk": "high",
            }
        ],
        calibration_freshness="not_yet_calibrated",
    )
    assert set(payload) == d1.PAYLOAD_KEYS
    assert payload["method_config"] == {"calibration_freshness": "not_yet_calibrated"}


def test_forward_and_reverse_payloads_are_directionally_distinct_and_deterministic(tmp_path: Path) -> None:
    repo, base, head = _fixture_repo(tmp_path)
    base_sources, _ = d1._source_snapshot(repo, base)
    head_sources, _ = d1._source_snapshot(repo, head)
    forward_paths = d1._changed_paths(repo, base, head)
    reverse_paths = d1._changed_paths(repo, head, base)
    assert forward_paths == reverse_paths

    forward = d1._payload(
        repo="owner/repo",
        baseline_sha=base,
        candidate_sha=head,
        baseline_sources=base_sources,
        candidate_sources=head_sources,
        production_diff=d1._production_diff(repo, base, head, forward_paths),
        behavior_catalog=[],
        calibration_freshness="not_yet_calibrated",
    )
    reverse = d1._payload(
        repo="owner/repo",
        baseline_sha=head,
        candidate_sha=base,
        baseline_sources=head_sources,
        candidate_sources=base_sources,
        production_diff=d1._production_diff(repo, head, base, reverse_paths),
        behavior_catalog=[],
        calibration_freshness="not_yet_calibrated",
    )
    assert d1._sha256_json(forward) == d1._sha256_json(copy.deepcopy(forward))
    assert d1._sha256_json(forward) != d1._sha256_json(reverse)
    assert forward["base_sha"] == reverse["head_sha"]
    assert forward["head_sha"] == reverse["base_sha"]


def test_materializer_has_no_big_import_or_candidate_invocation() -> None:
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


def _synthetic_valid_manifest() -> dict[str, object]:
    corpus = json.loads(d1.CORPUS_PATH.read_text(encoding="utf-8"))
    gate_d = json.loads(d1.GATE_D_PATH.read_text(encoding="utf-8"))
    cases = [case for case in corpus["cases"] if d1._evaluation_case(case)]
    rows: list[dict[str, object]] = []
    for case in sorted(cases, key=lambda item: item["case_id"]):
        run_key = d1.candidate_case_envelope(case)["run_key"]
        for direction in d1.DIRECTIONS:
            baseline, candidate = (
                (case["base_sha"], case["head_sha"]) if direction == "forward" else (case["head_sha"], case["base_sha"])
            )
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
                    "behavior_catalog_digest": "1" * 64,
                    "baseline_source": {
                        "file_count": 0,
                        "nonregular_python_paths": [],
                        "snapshot_digest": "2" * 64,
                    },
                    "candidate_source": {
                        "file_count": 0,
                        "nonregular_python_paths": [],
                        "snapshot_digest": "3" * 64,
                    },
                    "production_diff_digest": "4" * 64,
                    "production_diff_bytes": 0,
                    "candidate_payload_top_level_keys": sorted(d1.PAYLOAD_KEYS),
                    "candidate_payload_digest": "5" * 64,
                    "leakage_assertion": "passed",
                }
            )
    rows.sort(key=lambda row: (str(row["run_key"]), str(row["direction"])))
    payload_set = [
        {"run_key": row["run_key"], "direction": row["direction"], "payload_digest": row["candidate_payload_digest"]}
        for row in rows
    ]
    core: dict[str, object] = {
        "schema_version": "1.0",
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
        "candidate_payload_keys": sorted(d1.PAYLOAD_KEYS),
        "candidate_imported_during_materialization": False,
        "candidate_execution_permitted": False,
        "evaluation_case_count": len(cases),
        "case_direction_count": len(rows),
        "candidate_visible_payload_set_digest": d1v._sha256_json(payload_set),
        "rows": rows,
        "materialization_failures": [],
    }
    manifest = dict(core)
    manifest["input_manifest_digest"] = d1v._sha256_json(core)
    return manifest


def test_manifest_validator_rejects_observation_leakage_and_posthoc_drift() -> None:
    valid = _synthetic_valid_manifest()
    assert d1v.validate_manifest(valid) == []

    imported = copy.deepcopy(valid)
    imported["candidate_imported_during_materialization"] = True
    assert any("must not be imported" in item for item in d1v.validate_manifest(imported))

    widened_visibility = copy.deepcopy(valid)
    widened_visibility["candidate_payload_keys"] = sorted([*d1.PAYLOAD_KEYS, "case_id"])
    assert any("payload key" in item for item in d1v.validate_manifest(widened_visibility))

    calibrated = copy.deepcopy(valid)
    calibrated["calibration_freshness"] = "fresh"
    assert any("cold-start" in item for item in d1v.validate_manifest(calibrated))

    missing = copy.deepcopy(valid)
    missing["rows"] = missing["rows"][:-1]
    missing_core = dict(missing)
    missing_core.pop("input_manifest_digest")
    missing["input_manifest_digest"] = d1v._sha256_json(missing_core)
    assert any("both directions" in item or "missing direction" in item for item in d1v.validate_manifest(missing))
