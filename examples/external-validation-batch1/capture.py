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
            "ANONYMIZED_TELEMETRY": "false",
            "DO_NOT_TRACK": "1",
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
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "probe_error": f"TimeoutExpired: probe exceeded {exc.timeout}s",
            "process_exit_code": None,
        }

    payload: dict[str, Any] | None = None
    parse_error: str | None = None
    for line in reversed(completed.stdout.splitlines()):
        if not line.startswith(PREFIX):
            continue
        try:
            value = json.loads(line[len(PREFIX) :])
        except json.JSONDecodeError as exc:
            parse_error = f"ProbeProtocolError: invalid JSON payload: {exc}"
            break
        if not isinstance(value, dict):
            parse_error = "ProbeProtocolError: payload must be a JSON object"
            break
        payload = value
        break

    if payload is None:
        payload = {"probe_error": parse_error or "ProbeProtocolError: no PROOFDIFF_PROBE payload emitted"}

    payload["process_exit_code"] = completed.returncode
    if completed.returncode != 0 and payload.get("probe_error") is None:
        payload["probe_error"] = f"ProbeProcessError: exit code {completed.returncode}"
    if completed.stderr.strip():
        payload["stderr_tail"] = completed.stderr.strip()[-4000:]
    return payload


def _normalized_observation(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"process_exit_code", "stderr_tail"}
    }


def capture(python: Path, probe: Path, revision: str, runs: int) -> dict[str, Any]:
    observations = [_run_once(python, probe) for _ in range(runs)]
    normalized = [_normalized_observation(item) for item in observations]
    return {
        "schema_version": "1",
        "revision": revision,
        "runs": observations,
        "summary": {
            "runs": runs,
            "probe_error_runs": sum(item.get("probe_error") is not None for item in observations),
            "nonzero_exit_runs": sum(item.get("process_exit_code") not in {0} for item in observations),
            "stable": all(item == normalized[0] for item in normalized[1:]) if normalized else False,
        },
    }


def _capture_is_valid(result: dict[str, Any]) -> bool:
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        summary.get("probe_error_runs") == 0
        and summary.get("nonzero_exit_runs") == 0
        and summary.get("stable") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture an external ProofDiff validation probe.")
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs <= 0 or args.runs > 20:
        raise SystemExit("--runs must be between 1 and 20")

    result = capture(args.python.absolute(), args.probe.resolve(), args.revision, args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))

    # Always persist the raw evidence first, then fail closed. This prevents a
    # deterministic environment/protocol failure from being mistaken for a
    # successful behavioral capture and defers no error to the translation step.
    if not _capture_is_valid(result):
        print(f"invalid external capture written to {args.output}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
