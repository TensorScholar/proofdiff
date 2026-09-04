from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmarks.phase8b.harness import (
    assert_candidate_payload_no_leakage,
    candidate_case_envelope,
    derive_behavior_catalog,
    is_candidate_source_path,
)

ROOT = Path(__file__).parents[2]
PHASE = ROOT / "benchmarks" / "phase8b"
CORPUS_PATH = PHASE / "corpus.json"
GATE_D_PATH = PHASE / "gate_d.json"
STATIC_RULES_PATH = PHASE / "static_rules.json"

CANDIDATE_VISIBLE_FIELDS = {
    "repo",
    "base_sha",
    "head_sha",
    "sanitized_baseline_source",
    "sanitized_candidate_source",
    "production_diff",
    "behavior_catalog",
    "method_config",
}
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for chunk in encoder.iterencode(value):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_text(value) + "\n", encoding="utf-8")


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _eligible_case(case: dict[str, Any]) -> bool:
    return (case.get("arm") == "historical" and case.get("eligibility") == "qualified") or (
        case.get("arm") == "control" and case.get("eligibility") == "control"
    )


def _normalize_path(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")


def _safe_repo_slug(repo: str) -> str:
    if not REPO_RE.fullmatch(repo):
        raise ValueError(f"invalid frozen repository name: {repo!r}")
    return repo.replace("/", "__")


def _validate_sha(value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"invalid frozen commit SHA: {value!r}")
    return value


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(
    git_dir: Path,
    *args: str,
    text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", *args],
        check=True,
        capture_output=True,
        text=text,
        env=_git_env(),
    )


def _prepare_repo(cache_root: Path, repo: str, shas: set[str]) -> Path:
    slug = _safe_repo_slug(repo)
    git_dir = cache_root / "repos" / f"{slug}.git"
    if git_dir.exists():
        raise RuntimeError(f"materialization cache collision: {git_dir}")
    git_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--bare", str(git_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    _git(git_dir, "remote", "add", "origin", f"https://github.com/{repo}.git")
    frozen_shas = sorted(_validate_sha(sha) for sha in shas)
    _git(git_dir, "fetch", "--no-tags", "--depth=1", "origin", *frozen_shas)
    for sha in frozen_shas:
        resolved = _git(git_dir, "rev-parse", f"{sha}^{{commit}}").stdout.strip()
        if resolved != sha:
            raise RuntimeError(f"frozen revision verification failed for {repo}@{sha}: got {resolved}")
    return git_dir


def _decode_python_source(data: bytes, *, path: str) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        return data.decode(encoding)
    except (LookupError, SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"cannot decode Python source using PEP 263 rules: {path}") from exc


def _source_snapshot(git_dir: Path, *, repo: str, sha: str) -> dict[str, Any]:
    process = subprocess.Popen(
        ["git", f"--git-dir={git_dir}", "archive", "--format=tar", sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_env(),
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("git archive did not expose expected pipes")

    sources: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                path = _normalize_path(member.name)
                if not is_candidate_source_path(path) or not path.endswith(".py"):
                    continue
                if not member.isfile():
                    raise RuntimeError(f"unsupported candidate Python source entry type: {repo}@{sha}:{path}")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f"failed to read archived source: {repo}@{sha}:{path}")
                if path in sources:
                    raise RuntimeError(f"duplicate normalized source path: {repo}@{sha}:{path}")
                sources[path] = _decode_python_source(extracted.read(), path=path)
    finally:
        process.stdout.close()

    stderr = process.stderr.read().decode("utf-8", errors="replace")
    process.stderr.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"git archive failed for {repo}@{sha}: {stderr.strip()}")

    ordered_sources = {path: sources[path] for path in sorted(sources)}
    if not ordered_sources:
        raise RuntimeError(f"no candidate-relevant Python source found for {repo}@{sha}")
    return {
        "schema_version": "1.0",
        "repo": repo,
        "sha": sha,
        "source_projection": "frozen_candidate_path_filter_and_locked_candidate_python_suffix",
        "source_count": len(ordered_sources),
        "sources": ordered_sources,
        "source_digest": canonical_sha256(ordered_sources),
    }


def _changed_paths(git_dir: Path, *, base_sha: str, head_sha: str) -> list[str]:
    completed = _git(
        git_dir,
        "diff",
        "--no-ext-diff",
        "--no-renames",
        "--name-only",
        "-z",
        base_sha,
        head_sha,
        text=False,
    )
    raw = completed.stdout
    paths: set[str] = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            decoded = item.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("Git returned a non-UTF-8 changed pathname") from exc
        normalized = _normalize_path(decoded)
        if is_candidate_source_path(normalized):
            paths.add(normalized)
    return sorted(paths)


def _production_diff(git_dir: Path, *, base_sha: str, head_sha: str) -> dict[str, Any]:
    changed_paths = _changed_paths(git_dir, base_sha=base_sha, head_sha=head_sha)
    if not changed_paths:
        raise RuntimeError(f"no production paths remain after frozen sanitization: {base_sha}..{head_sha}")
    completed = _git(
        git_dir,
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--no-renames",
        "--unified=3",
        base_sha,
        head_sha,
        "--",
        *changed_paths,
    )
    unified_diff = completed.stdout
    return {
        "changed_paths": changed_paths,
        "rename_policy": "disabled_decompose_to_delete_add",
        "unified_diff": unified_diff,
        "unified_diff_sha256": hashlib.sha256(unified_diff.encode("utf-8")).hexdigest(),
    }


def _candidate_payload(
    *,
    repo: str,
    base_sha: str,
    head_sha: str,
    baseline_sources: dict[str, str],
    candidate_sources: dict[str, str],
    production_diff: dict[str, Any],
    behavior_catalog: list[dict[str, Any]],
    method_config: dict[str, Any],
    expected_visible_fields: set[str] = CANDIDATE_VISIBLE_FIELDS,
) -> dict[str, Any]:
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
    if set(payload) != expected_visible_fields:
        raise RuntimeError(
            f"candidate-visible payload keys drifted: expected {sorted(expected_visible_fields)}, got {sorted(payload)}"
        )
    assert_candidate_payload_no_leakage(payload)
    return payload


def _locked_blob_inventory(gate_d: dict[str, Any]) -> dict[str, str]:
    frozen_inputs = gate_d["frozen_inputs"]
    return {
        "protocol_blob_sha": _git_blob_sha(GATE_D_PATH),
        "corpus_blob_sha": str(frozen_inputs["corpus"]["git_blob_sha"]),
        "gate_b_blob_sha": str(frozen_inputs["gate_b"]["git_blob_sha"]),
        "static_rules_blob_sha": str(frozen_inputs["static_rules"]["git_blob_sha"]),
        "harness_blob_sha": str(frozen_inputs["harness"]["git_blob_sha"]),
        "methods_blob_sha": str(frozen_inputs["methods"]["git_blob_sha"]),
        "candidate_blob_sha": str(frozen_inputs["candidate"]["git_blob_sha"]),
    }


def materialize(*, output_root: Path, cache_root: Path) -> dict[str, Any]:
    corpus = _load_json(CORPUS_PATH)
    gate_d = _load_json(GATE_D_PATH)
    rules = _load_json(STATIC_RULES_PATH)

    if gate_d.get("protocol_status") != "frozen":
        raise RuntimeError("Gate D protocol must be frozen before D1 materialization")
    execution = gate_d.get("execution_design", {})
    protocol_fields = set(execution.get("candidate_visible_fields", []))
    if protocol_fields != CANDIDATE_VISIBLE_FIELDS:
        raise RuntimeError("Gate D candidate-visible field boundary does not match the D1 materializer")
    if gate_d.get("D1_input_materialization", {}).get("candidate_execution_forbidden") is not True:
        raise RuntimeError("Gate D must explicitly forbid candidate execution during D1")

    raw_cases = corpus.get("cases", [])
    cases = [case for case in raw_cases if isinstance(case, dict) and _eligible_case(case)]
    if not cases:
        raise RuntimeError("frozen corpus contains no materializable cases")

    catalogs = derive_behavior_catalog(corpus)
    required_revisions: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        repo = str(case["repo"])
        _safe_repo_slug(repo)
        required_revisions[repo].update({_validate_sha(str(case["base_sha"])), _validate_sha(str(case["head_sha"]))})

    repo_dirs = {repo: _prepare_repo(cache_root, repo, shas) for repo, shas in sorted(required_revisions.items())}

    snapshot_cache: dict[tuple[str, str], dict[str, Any]] = {}
    snapshot_refs: dict[tuple[str, str], str] = {}
    for repo, shas in sorted(required_revisions.items()):
        repo_slug = _safe_repo_slug(repo)
        for sha in sorted(shas):
            snapshot = _source_snapshot(repo_dirs[repo], repo=repo, sha=sha)
            relative = f"snapshots/{repo_slug}/{sha}.json"
            _write_json(output_root / relative, snapshot)
            snapshot_cache[(repo, sha)] = snapshot
            snapshot_refs[(repo, sha)] = relative

    catalog_refs: dict[str, str] = {}
    for repo, catalog in sorted(catalogs.items()):
        relative = f"catalogs/{_safe_repo_slug(repo)}.json"
        _write_json(output_root / relative, catalog)
        catalog_refs[repo] = relative

    method_config_ref = "method_config.json"
    _write_json(output_root / method_config_ref, rules)

    run_records: list[dict[str, Any]] = []
    directions = gate_d.get("execution_design", {}).get("directions")
    if directions != ["forward", "reverse"]:
        raise RuntimeError("D1 materializer requires the frozen forward/reverse direction order")

    for case in sorted(cases, key=lambda item: str(item["case_id"])):
        repo = str(case["repo"])
        original_base = _validate_sha(str(case["base_sha"]))
        original_head = _validate_sha(str(case["head_sha"]))
        envelope = candidate_case_envelope(case)
        behavior_catalog = catalogs.get(repo)
        if not behavior_catalog:
            raise RuntimeError(f"missing derived behavior catalog for {repo}")

        for direction in directions:
            if direction == "forward":
                base_sha, head_sha = original_base, original_head
            else:
                base_sha, head_sha = original_head, original_base

            baseline_snapshot = snapshot_cache[(repo, base_sha)]
            candidate_snapshot = snapshot_cache[(repo, head_sha)]
            production_diff = _production_diff(repo_dirs[repo], base_sha=base_sha, head_sha=head_sha)
            payload = _candidate_payload(
                repo=repo,
                base_sha=base_sha,
                head_sha=head_sha,
                baseline_sources=dict(baseline_snapshot["sources"]),
                candidate_sources=dict(candidate_snapshot["sources"]),
                production_diff=production_diff,
                behavior_catalog=behavior_catalog,
                method_config=rules,
                expected_visible_fields=protocol_fields,
            )
            payload_digest = canonical_sha256(payload)
            run_id = f"{envelope['run_key']}-{direction}"
            descriptor = {
                "schema_version": "1.0",
                "run_id": run_id,
                "run_key": envelope["run_key"],
                "case_id": case["case_id"],
                "arm": case["arm"],
                "eligibility": case["eligibility"],
                "direction": direction,
                "repo": repo,
                "base_sha": base_sha,
                "head_sha": head_sha,
                "baseline_snapshot_ref": snapshot_refs[(repo, base_sha)],
                "candidate_snapshot_ref": snapshot_refs[(repo, head_sha)],
                "behavior_catalog_ref": catalog_refs[repo],
                "method_config_ref": method_config_ref,
                "production_diff": production_diff,
                "candidate_payload_keys": sorted(payload),
                "candidate_payload_digest": payload_digest,
                "leakage_check": "passed",
                "candidate_invoked": False,
            }
            descriptor_ref = f"runs/{run_id}.json"
            _write_json(output_root / descriptor_ref, descriptor)
            run_records.append(
                {
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "arm": case["arm"],
                    "eligibility": case["eligibility"],
                    "direction": direction,
                    "repo": repo,
                    "base_sha": base_sha,
                    "head_sha": head_sha,
                    "descriptor_ref": descriptor_ref,
                    "candidate_payload_digest": payload_digest,
                    "changed_path_count": len(production_diff["changed_paths"]),
                }
            )

    snapshot_inventory = [
        {
            "repo": repo,
            "sha": sha,
            "snapshot_ref": snapshot_refs[(repo, sha)],
            "source_count": int(snapshot_cache[(repo, sha)]["source_count"]),
            "source_digest": str(snapshot_cache[(repo, sha)]["source_digest"]),
        }
        for repo, sha in sorted(snapshot_cache)
    ]
    manifest_core = {
        "schema_version": "1.0",
        "phase": "8B",
        "gate": "D1",
        "materialization_status": "complete",
        "candidate_execution_count": 0,
        "candidate_execution_attestation": "minimal_big_v1 was not imported or invoked during materialization",
        "network_role": "evaluator_only",
        "fetch_policy": "github_repo_exact_frozen_sha_only",
        "rename_policy": "disabled_decompose_to_delete_add",
        "source_projection": "frozen_candidate_path_filter_and_locked_candidate_python_suffix",
        "locked_blobs": _locked_blob_inventory(gate_d),
        "case_count": len(cases),
        "run_count": len(run_records),
        "repository_count": len(required_revisions),
        "snapshot_count": len(snapshot_inventory),
        "candidate_visible_fields": sorted(protocol_fields),
        "snapshot_inventory": snapshot_inventory,
        "runs": sorted(run_records, key=lambda item: str(item["run_id"])),
    }
    manifest = dict(manifest_core)
    manifest["input_manifest_digest"] = canonical_sha256(manifest_core)
    _write_json(output_root / "gate_d_input_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()

    output_root = args.output.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(f"output directory must be empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    if args.cache is not None:
        cache_root = args.cache.resolve()
        cache_root.mkdir(parents=True, exist_ok=True)
        manifest = materialize(output_root=output_root, cache_root=cache_root)
    else:
        with tempfile.TemporaryDirectory(prefix="proofdiff-gate-d1-") as temporary:
            manifest = materialize(output_root=output_root, cache_root=Path(temporary))

    print(
        "Gate D1 materialization complete: "
        f"cases={manifest['case_count']} runs={manifest['run_count']} "
        f"snapshots={manifest['snapshot_count']} digest={manifest['input_manifest_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
