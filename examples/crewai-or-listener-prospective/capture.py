from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

PREFIX = "PROOFDIFF_PROBE="


def _run_once(python: Path, probe: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "CREWAI_DISABLE_TELEMETRY": "true",
            "CREWAI_DISABLE_TRACKING": "true",
            "OTEL_SDK_DISABLED": "true",
            "PYTHONUNBUFFERED": "1",
        }
    )
    try:
        completed = subprocess.run(
            [str(python), str(probe)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "completed": [],
            "joined": 0,
            "runtime_error": f"TimeoutExpired: probe exceeded {exc.timeout}s",
            "process_exit_code": None,
        }

    payload: dict[str, Any] | None = None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(PREFIX):
            candidate = json.loads(line[len(PREFIX) :])
            if not isinstance(candidate, dict):
                raise ValueError("probe payload must be a JSON object")
            payload = candidate
            break

    if payload is None:
        payload = {
            "completed": [],
            "joined": 0,
            "runtime_error": "ProbeProtocolError: no PROOFDIFF_PROBE payload emitted",
        }
    if completed.returncode != 0 and payload.get("runtime_error") is None:
        payload["runtime_error"] = f"ProbeProcessError: exit code {completed.returncode}"
    payload["process_exit_code"] = completed.returncode
    if completed.stderr.strip():
        payload["stderr_tail"] = completed.stderr.strip()[-4000:]
    return payload


def capture(python: Path, probe: Path, revision: str, runs: int) -> dict[str, Any]:
    observations = [_run_once(python, probe) for _ in range(runs)]
    incomplete_runs = 0
    join_violation_runs = 0
    runtime_error_runs = 0
    for observation in observations:
        completed = observation.get("completed")
        if not isinstance(completed, list) or sorted(completed) != ["fast", "slow"]:
            incomplete_runs += 1
        if observation.get("joined") != 1:
            join_violation_runs += 1
        if observation.get("runtime_error") is not None:
            runtime_error_runs += 1

    return {
        "schema_version": "1",
        "revision": revision,
        "runs": observations,
        "summary": {
            "runs": runs,
            "incomplete_runs": incomplete_runs,
            "join_violation_runs": join_violation_runs,
            "runtime_error_runs": runtime_error_runs,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the frozen CrewAI OR-listener probe repeatedly.")
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs <= 0 or args.runs > 100:
        raise SystemExit("--runs must be between 1 and 100")

    # Preserve the virtual-environment interpreter path. resolve() follows the
    # venv's python symlink to the host interpreter and drops the venv context.
    result = capture(args.python.absolute(), args.probe.resolve(), args.revision, args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
