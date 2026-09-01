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
        raise AssertionError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AssertionError(f"expected JSON object record: {path}")
        records.append(value)
    return records


def _record_by_id(records: list[dict[str, Any]], contract_id: str) -> dict[str, Any]:
    matches = [record for record in records if record.get("contract_id") == contract_id]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one record for {contract_id}, found {len(matches)}")
    return matches[0]


def _capture_summary(path: Path, expected_revision: str) -> dict[str, int]:
    capture = _load_json(path)
    assert capture.get("revision") == expected_revision, capture.get("revision")
    summary = capture.get("summary")
    assert isinstance(summary, dict), summary
    result: dict[str, int] = {}
    for key in ("runs", "incomplete_runs", "join_violation_runs", "runtime_error_runs"):
        value = summary.get(key)
        assert isinstance(value, int) and not isinstance(value, bool), (key, value)
        result[key] = value
    return result


def _verify_selection(evidence: Path, registration: dict[str, Any]) -> dict[str, Any]:
    selection = _load_json(evidence / "selection.json")
    expected = registration["expected_selection"]
    selected = selection.get("selected_ids")
    relevant = set(registration["relevant_contracts"])
    assert isinstance(selected, list), selected
    selected_set = set(selected)
    relevant_selected = len(selected_set & relevant)
    recall = relevant_selected / len(relevant)
    precision = relevant_selected / len(selected_set) if selected_set else 0.0

    assert selected == [CASE_ID], selected
    assert selection["selected_contracts"] == expected["selected_contracts"]
    assert selection["total_contracts"] == expected["total_contracts"]
    assert selection["fallback_applied"] is expected["fallback_applied"]
    assert selection["uncovered_changes"] == []
    assert abs(float(selection["reduction_ratio"]) - float(expected["selection_reduction_ratio"])) < 1e-12
    assert abs(recall - float(expected["relevant_contract_recall"])) < 1e-12
    assert abs(precision - float(expected["relevant_contract_precision"])) < 1e-12

    changeset = _load_json(evidence / "changeset.json")
    changes = changeset.get("changes")
    assert isinstance(changes, list) and len(changes) == 1, changes
    assert changes[0]["type"] == "SOURCE_CODE_CHANGED"
    assert changes[0]["path"] == "source"
    return {
        "selected_ids": selected,
        "selected_contracts": selection["selected_contracts"],
        "total_contracts": selection["total_contracts"],
        "reduction_ratio": selection["reduction_ratio"],
        "fallback_applied": selection["fallback_applied"],
    }


def _verify_run(
    evidence: Path,
    *,
    expected_decision: str,
    expected_candidate: str,
    expected_comparison: str,
) -> dict[str, str]:
    decision = _load_json(evidence / "decision.json")
    assert decision["status"] == expected_decision, decision
    candidate = _record_by_id(_load_jsonl(evidence / "candidate-results.jsonl"), CASE_ID)
    assert candidate["status"] == expected_candidate, candidate
    comparison = _record_by_id(_load_jsonl(evidence / "comparisons.jsonl"), CASE_ID)
    assert comparison["classification"] == expected_comparison, comparison
    return {
        "decision": decision["status"],
        "candidate_contract_status": candidate["status"],
        "comparison": comparison["classification"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the preregistered CrewAI prospective pilot outcomes.")
    parser.add_argument("--base-capture", type=Path, required=True)
    parser.add_argument("--candidate-capture", type=Path, required=True)
    parser.add_argument("--repair-evidence", type=Path, required=True)
    parser.add_argument("--regression-evidence", type=Path, required=True)
    parser.add_argument("--preregistration-sha", required=True)
    parser.add_argument("--results-out", type=Path, required=True)
    args = parser.parse_args()

    registration = _load_json(PILOT_ROOT / "registration.json")
    target = registration["target"]
    assert isinstance(target, dict)
    base_sha = target["base_sha"]
    candidate_sha = target["candidate_sha"]
    assert isinstance(base_sha, str) and isinstance(candidate_sha, str)

    base_summary = _capture_summary(args.base_capture, base_sha)
    candidate_summary = _capture_summary(args.candidate_capture, candidate_sha)
    protocol = registration["probe_protocol"]
    assert isinstance(protocol, dict)
    assert base_summary["runs"] == protocol["runs_per_revision"] == 5
    assert candidate_summary["runs"] == protocol["runs_per_revision"]

    base_expected = protocol["baseline_bug_confirmation"]
    candidate_expected = protocol["candidate_acceptance"]
    assert base_summary["incomplete_runs"] >= base_expected["minimum_incomplete_runs"], base_summary
    assert base_summary["join_violation_runs"] <= base_expected["maximum_join_violation_runs"], base_summary
    assert candidate_summary["incomplete_runs"] <= candidate_expected["maximum_incomplete_runs"], candidate_summary
    assert candidate_summary["join_violation_runs"] <= candidate_expected["maximum_join_violation_runs"], candidate_summary
    assert candidate_summary["runtime_error_runs"] <= candidate_expected["maximum_runtime_error_runs"], candidate_summary

    repair_selection = _verify_selection(args.repair_evidence, registration)
    regression_selection = _verify_selection(args.regression_evidence, registration)
    assert repair_selection == regression_selection
    repair = _verify_run(
        args.repair_evidence,
        expected_decision="PASS",
        expected_candidate="pass",
        expected_comparison="fixed",
    )
    regression = _verify_run(
        args.regression_evidence,
        expected_decision="REVIEW",
        expected_candidate="fail",
        expected_comparison="new_regression",
    )

    results: dict[str, Any] = {
        "schema_version": "1",
        "pilot_id": registration["pilot_id"],
        "status": "passed_registered_prospective_gate",
        "preregistration_merge_sha": args.preregistration_sha,
        "target": {
            "repository": target["repository"],
            "issue": target["issue"],
            "pull_request": target["pull_request"],
            "base_sha": base_sha,
            "candidate_sha": candidate_sha,
        },
        "capture": {
            "base": base_summary,
            "candidate": candidate_summary,
        },
        "proofdiff": {
            "selection": repair_selection,
            "prospective_repair": repair,
            "counterfactual_regression": regression,
        },
        "claim_scope": "independent deterministic probe of the frozen CrewAI OR-listener behavior; not customer validation or general production recall",
    }
    args.results_out.parent.mkdir(parents=True, exist_ok=True)
    args.results_out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("PROOFDIFF_PILOT_RESULT=" + json.dumps(results, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
