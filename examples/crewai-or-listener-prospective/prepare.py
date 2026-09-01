from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PILOT_ROOT = Path(__file__).resolve().parent
CASE_ID = "flow.parallel_or_producers_complete"


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


def _summary(capture: dict[str, Any]) -> dict[str, int]:
    value = capture.get("summary")
    if not isinstance(value, dict):
        raise ValueError("capture is missing summary")
    keys = ("runs", "incomplete_runs", "join_violation_runs", "runtime_error_runs")
    result: dict[str, int] = {}
    for key in keys:
        item = value.get(key)
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ValueError(f"capture summary contains invalid {key}")
        result[key] = item
    return result


def _manifest(repository: str, commit: str, changed_paths: list[str]) -> dict[str, Any]:
    return {
        "agent": {"name": "crewai-flow-runtime", "version": "pr7184-prospective"},
        "runtime": {"model": "deterministic-flow", "provider": "local-python", "temperature": 0},
        "source": {"commit": commit, "paths": changed_paths, "repository": repository},
        "tools": [],
    }


def _trace(capture: dict[str, Any], repository: str, commit: str) -> dict[str, Any]:
    summary = _summary(capture)
    perfect = (
        summary["runs"] == 5
        and summary["incomplete_runs"] == 0
        and summary["join_violation_runs"] == 0
        and summary["runtime_error_runs"] == 0
    )
    if perfect:
        output = "all 5 probe runs preserved both producers and a single OR join"
    else:
        output = (
            f"{summary['incomplete_runs']} of {summary['runs']} probe runs had incomplete producer completion; "
            f"{summary['join_violation_runs']} join violations; {summary['runtime_error_runs']} runtime errors"
        )

    events: list[dict[str, Any]] = []
    raw_runs = capture.get("runs")
    if isinstance(raw_runs, list):
        for index, run in enumerate(raw_runs, start=1):
            if not isinstance(run, dict):
                continue
            completed = run.get("completed")
            events.append(
                {
                    "type": "probe",
                    "name": f"run_{index}",
                    "metadata": {
                        "completed": completed if isinstance(completed, list) else [],
                        "joined": run.get("joined"),
                        "runtime_error": run.get("runtime_error"),
                    },
                }
            )

    return {
        "case_id": CASE_ID,
        "events": events,
        "metadata": {
            "commit": commit,
            "evidence_kind": "independent_frozen_crewai_flow_probe",
            "repository": repository,
            "runs": summary["runs"],
        },
        "metrics": {
            "incomplete_runs": summary["incomplete_runs"],
            "join_violation_runs": summary["join_violation_runs"],
            "runtime_error_runs": summary["runtime_error_runs"],
        },
        "output": output,
    }


def prepare(base_capture_path: Path, candidate_capture_path: Path, output: Path) -> None:
    registration = _load_json(PILOT_ROOT / "registration.json")
    freeze = _load_json(PILOT_ROOT / "source-freeze.json")
    base_capture = _load_json(base_capture_path)
    candidate_capture = _load_json(candidate_capture_path)

    if registration.get("pilot_id") != "CREWAI-OR-PROSPECTIVE-001":
        raise ValueError("unexpected registration pilot_id")
    target = freeze.get("target")
    if not isinstance(target, dict):
        raise ValueError("source freeze is missing target")
    repository = target.get("repository")
    base_sha = target.get("base_sha")
    candidate_sha = target.get("candidate_sha")
    changed_paths = target.get("changed_paths")
    if not isinstance(repository, str) or not isinstance(base_sha, str) or not isinstance(candidate_sha, str):
        raise ValueError("source freeze contains invalid repository or revision metadata")
    if not isinstance(changed_paths, list) or not all(isinstance(item, str) for item in changed_paths):
        raise ValueError("source freeze contains invalid changed_paths")
    if base_capture.get("revision") != base_sha:
        raise ValueError("base capture revision does not match preregistered base SHA")
    if candidate_capture.get("revision") != candidate_sha:
        raise ValueError("candidate capture revision does not match preregistered candidate SHA")

    _write_json(output / "base-manifest.json", _manifest(repository, base_sha, changed_paths))
    _write_json(output / "candidate-manifest.json", _manifest(repository, candidate_sha, changed_paths))
    _write_trace(output / "base-traces.jsonl", _trace(base_capture, repository, base_sha))
    _write_trace(output / "candidate-traces.jsonl", _trace(candidate_capture, repository, candidate_sha))


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate frozen CrewAI probe captures into ProofDiff inputs.")
    parser.add_argument("--base-capture", type=Path, required=True)
    parser.add_argument("--candidate-capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.base_capture, args.candidate_capture, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
