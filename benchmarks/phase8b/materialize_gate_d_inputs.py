from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any

from benchmarks.phase8b.harness import (
    assert_candidate_payload_no_leakage,
    candidate_case_envelope,
    derive_behavior_catalog,
    is_candidate_source_path,
)

ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "benchmarks" / "phase8b"
CORPUS_PATH = PHASE / "corpus.json"
GATE_D_PATH = PHASE / "gate_d.json"
MATERIALIZER_PATH = PHASE / "materialize_gate_d_inputs.py"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DIRECTIONS = ("forward", "reverse")
PAYLOAD_KEYS = {
    "repo",
    "base_sha",
    "head_sha",
    "sanitized_baseline_source",
    "sanitized_candidate_source",
    "production_diff",
    "behavior_catalog",
    "method_config",
}
SOURCE_POLICY = "candidate_relevant_utf8_python_production_files_only_v1"
DIFF_POLICY = "git_diff_no_ext_no_color_no_renames_full_index_unified3_sanitized_paths_v1"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _git(repo_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _decode_python(path: str, data: bytes) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot deterministically decode Python source: {path}: {exc}") from exc


def _evaluation_case(case: dict[str, Any]) -> bool:
    return (case.get("arm") == "historical" and case.get("eligibility") == "qualified") or (
        case.get("arm") == "control" and case.get("eligibility") == "control"
    )


def _validate_repo(repo: str) -> None:
    if not REPO_RE.fullmatch(repo):
        raise ValueError(f"unsupported upstream repository slug: {repo!r}")


def _prepare_repo(*, repo: str, shas: set[str], work_root: Path) -> Path:
    _validate_repo(repo)
    repo_dir = work_root / repo.replace("/", "__")
    repo_dir.mkdir(parents=True, exist_ok=False)
    _git(repo_dir, "init", "--quiet")
    _git(repo_dir, "remote", "add", "origin", f"https://github.com/{repo}.git")
    for sha in sorted(shas):
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError(f"expected immutable 40-character SHA for {repo}: {sha!r}")
        _git(repo_dir, "fetch", "--quiet", "--no-tags", "--filter=blob:none", "--depth=1", "origin", sha)
        resolved = _git(repo_dir, "rev-parse", "FETCH_HEAD^{commit}").stdout.decode("ascii").strip()
        if resolved != sha:
            raise ValueError(f"upstream fetch identity mismatch for {repo}: expected {sha}, got {resolved}")
    return repo_dir


def _tree_entries(repo_dir: Path, sha: str) -> list[tuple[str, str]]:
    raw = _git(repo_dir, "ls-tree", "-r", "-z", sha).stdout
    entries: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0].decode("ascii")
        path = raw_path.decode("utf-8", errors="strict")
        entries.append((mode, path))
    return sorted(entries, key=lambda item: item[1])


def _source_snapshot(repo_dir: Path, sha: str) -> tuple[dict[str, str], dict[str, Any]]:
    sources: dict[str, str] = {}
    nonregular: list[str] = []
    for mode, path in _tree_entries(repo_dir, sha):
        if not path.endswith(".py") or not is_candidate_source_path(path):
            continue
        if not mode.startswith("100"):
            nonregular.append(path)
            continue
        data = _git(repo_dir, "show", f"{sha}:{path}").stdout
        sources[path] = _decode_python(path, data)
    metadata = {
        "file_count": len(sources),
        "nonregular_python_paths": nonregular,
        "snapshot_digest": _sha256_json(sources),
    }
    return {path: sources[path] for path in sorted(sources)}, metadata


def _changed_paths(repo_dir: Path, baseline_sha: str, candidate_sha: str) -> list[str]:
    raw = _git(repo_dir, "diff", "--name-only", "-z", "--no-renames", baseline_sha, candidate_sha).stdout
    paths = [item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item]
    return sorted(path for path in paths if is_candidate_source_path(path))


def _production_diff(repo_dir: Path, baseline_sha: str, candidate_sha: str, changed_paths: list[str]) -> str:
    if not changed_paths:
        return ""
    raw = _git(
        repo_dir,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--no-renames",
        "--full-index",
        "--unified=3",
        baseline_sha,
        candidate_sha,
        "--",
        *changed_paths,
    ).stdout
    return raw.decode("utf-8", errors="backslashreplace")


def _payload(
    *,
    repo: str,
    baseline_sha: str,
    candidate_sha: str,
    baseline_sources: dict[str, str],
    candidate_sources: dict[str, str],
    production_diff: str,
    behavior_catalog: list[dict[str, Any]],
    calibration_freshness: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "repo": repo,
        "base_sha": baseline_sha,
        "head_sha": candidate_sha,
        "sanitized_baseline_source": baseline_sources,
        "sanitized_candidate_source": candidate_sources,
        "production_diff": production_diff,
        "behavior_catalog": behavior_catalog,
        "method_config": {"calibration_freshness": calibration_freshness},
    }
    if set(payload) != PAYLOAD_KEYS:
        raise AssertionError("candidate payload key set drifted")
    assert_candidate_payload_no_leakage(payload)
    return payload


def materialize(*, work_root: Path) -> dict[str, Any]:
    corpus = _load_json(CORPUS_PATH)
    gate_d = _load_json(GATE_D_PATH)
    if gate_d.get("protocol_status") != "frozen":
        raise ValueError("Gate D protocol must be frozen before D1 materialization")
    if gate_d.get("observation_state_at_protocol_creation") != "unobserved":
        raise ValueError("Gate D protocol lost its unobserved-at-creation attestation")

    calibration_freshness = str(gate_d["execution_design"]["candidate_calibration_freshness"])
    if calibration_freshness != "not_yet_calibrated":
        raise ValueError("D1 must preserve the frozen cold-start calibration state")

    cases = [case for case in corpus.get("cases", []) if isinstance(case, dict) and _evaluation_case(case)]
    catalogs = derive_behavior_catalog(corpus)
    repo_shas: dict[str, set[str]] = {}
    for case in cases:
        repo = str(case["repo"])
        repo_shas.setdefault(repo, set()).update({str(case["base_sha"]), str(case["head_sha"])})

    work_root.mkdir(parents=True, exist_ok=False)
    repo_dirs = {
        repo: _prepare_repo(repo=repo, shas=shas, work_root=work_root) for repo, shas in sorted(repo_shas.items())
    }

    snapshot_cache: dict[tuple[str, str], tuple[dict[str, str], dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for case in sorted(cases, key=lambda item: str(item.get("case_id"))):
        repo = str(case["repo"])
        frozen_base = str(case["base_sha"])
        frozen_head = str(case["head_sha"])
        run_key = candidate_case_envelope(case)["run_key"]
        catalog = catalogs.get(repo, [])
        catalog_digest = _sha256_json(catalog)
        repo_dir = repo_dirs[repo]

        for direction in DIRECTIONS:
            baseline_sha, candidate_sha = (
                (frozen_base, frozen_head) if direction == "forward" else (frozen_head, frozen_base)
            )
            try:
                for sha in (baseline_sha, candidate_sha):
                    key = (repo, sha)
                    if key not in snapshot_cache:
                        snapshot_cache[key] = _source_snapshot(repo_dir, sha)
                baseline_sources, baseline_meta = snapshot_cache[(repo, baseline_sha)]
                candidate_sources, candidate_meta = snapshot_cache[(repo, candidate_sha)]
                changed_paths = _changed_paths(repo_dir, baseline_sha, candidate_sha)
                diff = _production_diff(repo_dir, baseline_sha, candidate_sha, changed_paths)
                payload = _payload(
                    repo=repo,
                    baseline_sha=baseline_sha,
                    candidate_sha=candidate_sha,
                    baseline_sources=baseline_sources,
                    candidate_sources=candidate_sources,
                    production_diff=diff,
                    behavior_catalog=catalog,
                    calibration_freshness=calibration_freshness,
                )
                rows.append(
                    {
                        "case_id": case.get("case_id"),
                        "arm": case.get("arm"),
                        "eligibility": case.get("eligibility"),
                        "family_id": case.get("family_id"),
                        "run_key": run_key,
                        "direction": direction,
                        "repo": repo,
                        "baseline_sha": baseline_sha,
                        "candidate_sha": candidate_sha,
                        "changed_paths": changed_paths,
                        "behavior_catalog_digest": catalog_digest,
                        "baseline_source": baseline_meta,
                        "candidate_source": candidate_meta,
                        "production_diff_digest": _sha256(diff.encode("utf-8")),
                        "production_diff_bytes": len(diff.encode("utf-8")),
                        "candidate_payload_top_level_keys": sorted(payload),
                        "candidate_payload_digest": _sha256_json(payload),
                        "leakage_assertion": "passed",
                    }
                )
            except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
                failures.append(f"{case.get('case_id')}:{direction}:{type(exc).__name__}:{exc}")

    ordered_rows = sorted(rows, key=lambda row: (str(row["run_key"]), str(row["direction"])))
    payload_set = [
        {"run_key": row["run_key"], "direction": row["direction"], "payload_digest": row["candidate_payload_digest"]}
        for row in ordered_rows
    ]
    core = {
        "schema_version": "1.0",
        "phase": "8B",
        "gate": "D",
        "subgate": "D1",
        "materialization_status": "materialized" if not failures else "blocked",
        "protocol_blob_sha": _git_blob_sha(GATE_D_PATH),
        "corpus_blob_sha": _git_blob_sha(CORPUS_PATH),
        "materializer_blob_sha": _git_blob_sha(MATERIALIZER_PATH),
        "candidate_id": gate_d["frozen_inputs"]["candidate"]["id"],
        "candidate_blob_sha": gate_d["frozen_inputs"]["candidate"]["git_blob_sha"],
        "calibration_freshness": calibration_freshness,
        "source_snapshot_policy": SOURCE_POLICY,
        "production_diff_policy": DIFF_POLICY,
        "candidate_payload_keys": sorted(PAYLOAD_KEYS),
        "candidate_imported_during_materialization": any(name.endswith("big_candidate") for name in sys.modules),
        "candidate_execution_permitted": False,
        "evaluation_case_count": len(cases),
        "case_direction_count": len(ordered_rows),
        "candidate_visible_payload_set_digest": _sha256_json(payload_set),
        "rows": ordered_rows,
        "materialization_failures": sorted(failures),
    }
    manifest = dict(core)
    manifest["input_manifest_digest"] = _sha256_json(core)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = materialize(work_root=args.work_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if manifest["materialization_failures"]:
        raise SystemExit("Gate D1 materialization blocked; see manifest failures")
    print(f"Gate D1 materialized {manifest['case_direction_count']} case-directions")
    print(f"input_manifest_digest={manifest['input_manifest_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
