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


def _verify_selection(evidence: Path, ground_truth: dict[str, Any]) -> None:
    selection = _load_json(evidence / "selection.json")
    expected = ground_truth["expected_selection"]
    selected = selection.get("selected_ids")
    relevant = set(ground_truth["relevant_contracts"])
    if not isinstance(selected, list):
        raise AssertionError("selection.selected_ids must be an array")
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


def _verify_run(evidence: Path, *, expected_decision: str, expected_candidate: str, expected_comparison: str) -> None:
    decision = _load_json(evidence / "decision.json")
    assert decision["status"] == expected_decision, decision

    candidate = _record_by_id(_load_jsonl(evidence / "candidate-results.jsonl"), CASE_ID)
    assert candidate["status"] == expected_candidate, candidate

    comparison = _record_by_id(_load_jsonl(evidence / "comparisons.jsonl"), CASE_ID)
    assert comparison["classification"] == expected_comparison, comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the registered AgentGuard PR #8 pilot outcomes.")
    parser.add_argument("--repair-evidence", type=Path, required=True)
    parser.add_argument("--regression-evidence", type=Path, required=True)
    args = parser.parse_args()

    ground_truth = _load_json(PILOT_ROOT / "ground-truth.json")
    _verify_selection(args.repair_evidence, ground_truth)
    _verify_selection(args.regression_evidence, ground_truth)
    _verify_run(
        args.repair_evidence,
        expected_decision="PASS",
        expected_candidate="pass",
        expected_comparison="fixed",
    )
    _verify_run(
        args.regression_evidence,
        expected_decision="REVIEW",
        expected_candidate="fail",
        expected_comparison="new_regression",
    )
    print("AgentGuard PR #8 retrospective pilot matches registered ground truth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
