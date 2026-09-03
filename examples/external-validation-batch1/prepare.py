from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n" for value in values),
        encoding="utf-8",
    )


def _case(slug: str) -> dict[str, Any]:
    registration = _load_json(ROOT / "registration.json")
    matches = [case for case in registration["cases"] if case.get("slug") == slug]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one registration case for {slug}")
    return matches[0]


def _observation(capture: dict[str, Any], expected_revision: str) -> dict[str, Any]:
    if capture.get("revision") != expected_revision:
        raise ValueError("capture revision does not match registration")
    summary = capture.get("summary")
    runs = capture.get("runs")
    if not isinstance(summary, dict) or not isinstance(runs, list) or not runs:
        raise ValueError("capture is incomplete")
    if summary.get("probe_error_runs") != 0 or summary.get("nonzero_exit_runs") != 0:
        raise ValueError(f"capture contains probe errors: {summary}")
    if summary.get("stable") is not True:
        raise ValueError(f"capture is not deterministic across repeated runs: {summary}")
    first = runs[0]
    if not isinstance(first, dict):
        raise ValueError("capture observation must be an object")
    return {
        key: value
        for key, value in first.items()
        if key not in {"process_exit_code", "stderr_tail"}
    }


def _common_manifest(case: dict[str, Any], commit: str) -> dict[str, Any]:
    return {
        "agent": {"name": case["slug"], "version": "external-validation-batch1"},
        "runtime": {"model": "deterministic-probe", "provider": "local-python", "temperature": 0},
        "source": {
            "repository": case["repository"],
            "commit": commit,
            "paths": case["changed_paths"],
        },
        "tools": [],
    }


def _trace(contract_id: str, passed: bool, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": contract_id,
        "events": [
            {
                "type": "probe_assertion",
                "name": contract_id,
                "metadata": {"passed": passed},
            }
        ],
        "output": f"OK:{contract_id}" if passed else f"FAIL:{contract_id}",
        "metrics": {"passed": 1 if passed else 0},
        "metadata": metadata or {},
    }


def _openai(case: dict[str, Any], commit: str, observation: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _common_manifest(case, commit)
    strict_schema = observation.get("strict_schema")
    if not isinstance(strict_schema, dict):
        raise ValueError("OpenAI probe did not emit strict_schema")
    manifest["tools"] = [
        {
            "name": "alias_tool",
            "description": "Probe tool whose generated input schema exercises chained aliases.",
            "risk": "high",
            "destructive": False,
            "input_schema": strict_schema,
        }
    ]
    checks = {
        "schema.chained_ref_preserves_type": observation.get("chained_ref_preserves_type") is True,
        "schema.direct_ref_preserves_type": observation.get("direct_ref_preserves_type") is True,
        "schema.invalid_ref_rejected": observation.get("invalid_ref_rejected") is True,
    }
    traces = [_trace(contract_id, passed, metadata={"revision": commit}) for contract_id, passed in checks.items()]
    return manifest, traces


def _copilotkit(case: dict[str, Any], commit: str, observation: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _common_manifest(case, commit)
    top = observation.get("top_level")
    sub = observation.get("subgraph")
    if not isinstance(top, dict) or not isinstance(sub, dict):
        raise ValueError("CopilotKit probe did not emit top_level/subgraph observations")
    checks = {
        "subgraph.frontend_tools_propagate": sub.get("frontend_tool_present") is True,
        "subgraph.app_context_propagates": sub.get("app_context_present") is True,
        "top_level.frontend_tools_propagate": top.get("frontend_tool_present") is True,
        "top_level.app_context_propagates": top.get("app_context_present") is True,
    }
    traces = [
        _trace(
            contract_id,
            passed,
            metadata={
                "revision": commit,
                "subgraph_error": sub.get("error"),
                "top_level_error": top.get("error"),
            },
        )
        for contract_id, passed in checks.items()
    ]
    return manifest, traces


def _langgraph(case: dict[str, Any], commit: str, observation: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _common_manifest(case, commit)
    manifest["tools"] = [
        {
            "name": "approval_tool",
            "description": "Probe tool representing approval-sensitive graph control flow.",
            "risk": "critical",
            "destructive": True,
            "input_schema": {
                "type": "object",
                "properties": {"some_val": {"type": "integer"}},
                "required": ["some_val"],
                "additionalProperties": False,
            },
        }
    ]
    checks = {
        "hitl.sync_wrapper_propagates_interrupt": observation.get("sync_wrapper_propagates_interrupt") is True,
        "hitl.async_wrapper_propagates_interrupt": observation.get("async_wrapper_propagates_interrupt") is True,
        "hitl.direct_interrupt_propagates": observation.get("direct_interrupt_propagates") is True,
        "tool_wrapper.ordinary_success_preserved": observation.get("ordinary_wrapped_tool_succeeds") is True,
    }
    traces = [_trace(contract_id, passed, metadata={"revision": commit}) for contract_id, passed in checks.items()]
    return manifest, traces


_BUILDERS = {
    "openai-agents-chained-ref": _openai,
    "copilotkit-subgraph-context": _copilotkit,
    "langgraph-interrupt-wrapper": _langgraph,
}


def prepare(slug: str, base_capture_path: Path, candidate_capture_path: Path, output: Path) -> None:
    case = _case(slug)
    base_capture = _load_json(base_capture_path)
    candidate_capture = _load_json(candidate_capture_path)
    base_observation = _observation(base_capture, case["base_sha"])
    candidate_observation = _observation(candidate_capture, case["candidate_sha"])
    builder = _BUILDERS[slug]

    base_manifest, base_traces = builder(case, case["base_sha"], base_observation)
    candidate_manifest, candidate_traces = builder(case, case["candidate_sha"], candidate_observation)

    _write_json(output / "base-manifest.json", base_manifest)
    _write_json(output / "candidate-manifest.json", candidate_manifest)
    _write_jsonl(output / "base-traces.jsonl", base_traces)
    _write_jsonl(output / "candidate-traces.jsonl", candidate_traces)
    _write_json(
        output / "observations.json",
        {
            "case": case,
            "base": base_observation,
            "candidate": candidate_observation,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate frozen external probe captures into ProofDiff inputs.")
    parser.add_argument("--case", choices=sorted(_BUILDERS), required=True)
    parser.add_argument("--base-capture", type=Path, required=True)
    parser.add_argument("--candidate-capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.case, args.base_capture, args.candidate_capture, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
