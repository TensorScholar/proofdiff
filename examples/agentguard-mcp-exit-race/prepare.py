from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PILOT_ROOT = Path(__file__).resolve().parent
CASE_ID = "mcp.natural_exit_after_output_eof"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_trace(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _manifest(repository: str, commit: str, changed_paths: list[str]) -> dict[str, Any]:
    return {
        "agent": {"name": "agentguard-mcp-stdio-proxy", "version": "pr8-retrospective"},
        "runtime": {"model": "deterministic-mcp-stdio", "provider": "local-subprocess", "temperature": 0},
        "source": {"commit": commit, "paths": changed_paths, "repository": repository},
        "tools": [],
    }


def _trace(repository: str, commit: str, *, fixed: bool) -> dict[str, Any]:
    if fixed:
        events = [
            {"name": "stdout_eof", "type": "process"},
            {"name": "child_exit", "type": "process"},
        ]
        output = "MCP server output drained; child exited naturally."
        metrics = {"exit_code": 0, "forced_shutdown": 0}
    else:
        events = [
            {"name": "stdout_eof", "type": "process"},
            {"name": "forced_termination", "type": "process"},
        ]
        output = "MCP server output drained; proxy classified shutdown as forced."
        metrics = {"exit_code": 1, "forced_shutdown": 1}
    return {
        "case_id": CASE_ID,
        "events": events,
        "metadata": {
            "commit": commit,
            "evidence_kind": "reconstructed_from_agentguard_pr8_source_and_regression_test",
            "repository": repository,
        },
        "metrics": metrics,
        "output": output,
    }


def prepare(output: Path) -> None:
    source = _load_json(PILOT_ROOT / "source-evidence.json")
    ground_truth = _load_json(PILOT_ROOT / "ground-truth.json")
    if source.get("pilot_id") != "AG-MCP-EXIT-001" or ground_truth.get("pilot_id") != "AG-MCP-EXIT-001":
        raise ValueError("pilot identifiers do not match AG-MCP-EXIT-001")
    relevant = ground_truth.get("relevant_contracts")
    if relevant != [CASE_ID]:
        raise ValueError("ground truth relevant-contract set changed unexpectedly")

    target = source.get("target")
    if not isinstance(target, dict):
        raise ValueError("source evidence is missing target metadata")
    repository = target.get("repository")
    buggy_sha = target.get("buggy_sha")
    fixed_sha = target.get("fixed_sha")
    changed_paths = target.get("changed_source_paths")
    if not isinstance(repository, str) or not isinstance(buggy_sha, str) or not isinstance(fixed_sha, str):
        raise ValueError("source evidence contains invalid repository or commit metadata")
    if not isinstance(changed_paths, list) or not all(isinstance(item, str) for item in changed_paths):
        raise ValueError("source evidence contains invalid changed_source_paths")

    _write_json(output / "buggy-manifest.json", _manifest(repository, buggy_sha, changed_paths))
    _write_json(output / "fixed-manifest.json", _manifest(repository, fixed_sha, changed_paths))
    _write_trace(output / "buggy-traces.jsonl", _trace(repository, buggy_sha, fixed=False))
    _write_trace(output / "fixed-traces.jsonl", _trace(repository, fixed_sha, fixed=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare frozen ProofDiff inputs for AgentGuard PR #8.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
