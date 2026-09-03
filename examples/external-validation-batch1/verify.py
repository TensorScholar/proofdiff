from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

EXPECTED_OBSERVATIONS: dict[str, dict[str, dict[str, bool]]] = {
    "openai-agents-chained-ref": {
        "base": {
            "chained_ref_preserves_type": False,
            "direct_ref_preserves_type": True,
            "invalid_ref_rejected": True,
        },
        "candidate": {
            "chained_ref_preserves_type": True,
            "direct_ref_preserves_type": True,
            "invalid_ref_rejected": True,
        },
    },
    "copilotkit-subgraph-context": {
        "base": {
            "subgraph.frontend_tool_present": False,
            "subgraph.app_context_present": False,
            "top_level.frontend_tool_present": True,
            "top_level.app_context_present": True,
        },
        "candidate": {
            "subgraph.frontend_tool_present": True,
            "subgraph.app_context_present": True,
            "top_level.frontend_tool_present": True,
            "top_level.app_context_present": True,
        },
    },
    "langgraph-interrupt-wrapper": {
        "base": {
            "sync_wrapper_propagates_interrupt": False,
            "async_wrapper_propagates_interrupt": False,
            "direct_interrupt_propagates": True,
            "ordinary_wrapped_tool_succeeds": True,
        },
        "candidate": {
            "sync_wrapper_propagates_interrupt": True,
            "async_wrapper_propagates_interrupt": True,
            "direct_interrupt_propagates": True,
            "ordinary_wrapped_tool_succeeds": True,
        },
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AssertionError(f"expected JSON object record: {path}")
        values.append(value)
    return values


def _case(slug: str) -> dict[str, Any]:
    registration = _load_json(ROOT / "registration.json")
    matches = [case for case in registration["cases"] if case.get("slug") == slug]
    assert len(matches) == 1, matches
    return matches[0]


def _capture(path: Path, revision: str) -> dict[str, Any]:
    capture = _load_json(path)
    assert capture["revision"] == revision, capture["revision"]
    summary = capture["summary"]
    assert summary["runs"] == 3, summary
    assert summary["probe_error_runs"] == 0, summary
    assert summary["nonzero_exit_runs"] == 0, summary
    assert summary["stable"] is True, summary
    first = capture["runs"][0]
    return {
        key: value
        for key, value in first.items()
        if key not in {"process_exit_code", "stderr_tail"}
    }


def _path_get(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _verify_observation(slug: str, side: str, observed: dict[str, Any]) -> None:
    expected = EXPECTED_OBSERVATIONS[slug][side]
    for path, wanted in expected.items():
        actual = _path_get(observed, path)
        assert actual is wanted, (slug, side, path, actual, wanted)


def _records_by_id(path: Path) -> dict[str, dict[str, Any]]:
    records = _load_jsonl(path)
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        contract_id = record.get("contract_id")
        assert isinstance(contract_id, str) and contract_id not in result, contract_id
        result[contract_id] = record
    return result


def _verify_targeted(
    evidence: Path,
    protected: list[str],
    *,
    expected_decision: str,
    expected_comparison: str,
    expected_candidate_status: str,
) -> dict[str, Any]:
    selection = _load_json(evidence / "selection.json")
    selected = selection["selected_ids"]
    assert selected == sorted(protected), (selected, protected)
    assert selection["selected_contracts"] == len(protected), selection
    assert selection["fallback_applied"] is False, selection
    assert selection["uncovered_changes"] == [], selection

    decision = _load_json(evidence / "decision.json")
    assert decision["status"] == expected_decision, decision

    candidates = _records_by_id(evidence / "candidate-results.jsonl")
    comparisons = _records_by_id(evidence / "comparisons.jsonl")
    for contract_id in protected:
        assert candidates[contract_id]["status"] == expected_candidate_status, candidates[contract_id]
        assert comparisons[contract_id]["classification"] == expected_comparison, comparisons[contract_id]

    return {
        "decision": decision["status"],
        "selected_ids": selected,
        "selected_contracts": selection["selected_contracts"],
        "total_contracts": selection["total_contracts"],
        "reduction_ratio": selection["reduction_ratio"],
        "fallback_applied": selection["fallback_applied"],
    }


def _verify_full(evidence: Path, protected: list[str]) -> dict[str, Any]:
    selection = _load_json(evidence / "selection.json")
    assert selection["selected_contracts"] == selection["total_contracts"], selection
    assert set(protected).issubset(set(selection["selected_ids"])), selection
    assert selection["fallback_applied"] is False, selection
    decision = _load_json(evidence / "decision.json")
    assert decision["status"] == "PASS", decision
    return {
        "decision": decision["status"],
        "selected_contracts": selection["selected_contracts"],
        "total_contracts": selection["total_contracts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify external Batch 1 without hiding null results.")
    parser.add_argument("--case", choices=sorted(EXPECTED_OBSERVATIONS), required=True)
    parser.add_argument("--base-capture", type=Path, required=True)
    parser.add_argument("--candidate-capture", type=Path, required=True)
    parser.add_argument("--repair-evidence", type=Path, required=True)
    parser.add_argument("--regression-evidence", type=Path, required=True)
    parser.add_argument("--full-evidence", type=Path, required=True)
    parser.add_argument("--results-out", type=Path, required=True)
    args = parser.parse_args()

    case = _case(args.case)
    protected = sorted(case["protected_contracts"])
    base = _capture(args.base_capture, case["base_sha"])
    candidate = _capture(args.candidate_capture, case["candidate_sha"])
    _verify_observation(args.case, "base", base)
    _verify_observation(args.case, "candidate", candidate)

    reverse_decision = "BLOCK" if case["risk"] == "critical" else "REVIEW"
    repair = _verify_targeted(
        args.repair_evidence,
        protected,
        expected_decision="PASS",
        expected_comparison="fixed",
        expected_candidate_status="pass",
    )
    regression = _verify_targeted(
        args.regression_evidence,
        protected,
        expected_decision=reverse_decision,
        expected_comparison="new_regression",
        expected_candidate_status="fail",
    )
    full = _verify_full(args.full_evidence, protected)

    static_ids = sorted(case["static_tag_baseline_contracts"])
    static_count = len(static_ids)
    targeted_count = repair["selected_contracts"]
    total = repair["total_contracts"]

    results = {
        "schema_version": "1",
        "batch_id": "PROOFDIFF-EXT-BATCH1-001",
        "case_id": case["id"],
        "case": args.case,
        "target": {
            "repository": case["repository"],
            "base_sha": case["base_sha"],
            "candidate_sha": case["candidate_sha"],
            "status": case["status"],
        },
        "oracle_reproduced": True,
        "proofdiff_v0_1_0": {
            "targeted_repair": repair,
            "reverse_regression": regression,
            "full_suite": full,
            "protected_behavior_omissions": sorted(set(protected) - set(repair["selected_ids"])),
            "false_safe_count": 0,
        },
        "baseline_comparison": {
            "full_suite_contracts": total,
            "static_tag_contracts": static_count,
            "proofdiff_targeted_contracts": targeted_count,
            "proofdiff_vs_full_avoided_contracts": total - targeted_count,
            "proofdiff_vs_static_contract_delta": targeted_count - static_count,
        },
        "claim_scope": (
            "deterministic micro-suite validation of frozen external revisions; "
            "suite-count reduction is not customer ROI, production recall, or safety proof"
        ),
    }
    assert results["proofdiff_v0_1_0"]["protected_behavior_omissions"] == []
    args.results_out.parent.mkdir(parents=True, exist_ok=True)
    args.results_out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PROOFDIFF_BATCH1_RESULT=" + json.dumps(results, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
