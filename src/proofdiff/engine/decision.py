from __future__ import annotations

from typing import Any

from proofdiff.domain.errors import InputError
from proofdiff.domain.models import (
    ChangeSet,
    Comparison,
    ContractResult,
    Decision,
    DecisionReason,
    DecisionStatus,
    ResultStatus,
    Risk,
    Selection,
    Severity,
)

DEFAULT_POLICY: dict[str, bool] = {
    "block_on_missing_critical": True,
    "block_on_new_critical_regression": True,
    "block_on_any_critical_failure": True,
    "review_on_uncovered_high_change": True,
    "review_on_high_risk_capability_change": True,
    "review_on_fallback": True,
    "review_on_empty_selection": True,
}


def validate_policy(value: dict[str, Any] | None) -> dict[str, bool]:
    if value is None:
        return dict(DEFAULT_POLICY)
    if not isinstance(value, dict):
        raise InputError("decision policy must be an object")
    unknown = sorted(set(value) - set(DEFAULT_POLICY))
    if unknown:
        raise InputError(f"decision policy contains unknown fields: {', '.join(unknown)}")
    effective = dict(DEFAULT_POLICY)
    for key, item in value.items():
        if not isinstance(item, bool):
            raise InputError(f"decision policy field {key} must be a boolean")
        effective[key] = item
    return effective


def _validate_inputs(
    selection: Selection,
    candidate_results: list[ContractResult],
    comparisons: list[Comparison],
) -> None:
    selected = set(selection.selected_ids)
    if len(selected) != len(selection.selected_ids):
        raise InputError("selection contains duplicate contract ids")
    candidate_ids = [item.contract_id for item in candidate_results]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise InputError("candidate results contain duplicate contract ids")
    unknown_candidate_ids = sorted(set(candidate_ids) - selected)
    if unknown_candidate_ids:
        raise InputError(f"candidate results reference unselected contracts: {', '.join(unknown_candidate_ids)}")
    comparison_ids = [item.contract_id for item in comparisons]
    if len(set(comparison_ids)) != len(comparison_ids):
        raise InputError("comparisons contain duplicate contract ids")
    unknown_comparison_ids = sorted(set(comparison_ids) - selected)
    if unknown_comparison_ids:
        raise InputError(f"comparisons reference unselected contracts: {', '.join(unknown_comparison_ids)}")
    if selection.total_contracts < len(selection.selected_ids):
        raise InputError("selection total_contracts is smaller than selected contract count")
    invalid_uncovered = [
        index
        for index in selection.uncovered_changes
        if isinstance(index, bool) or not isinstance(index, int) or index < 0
    ]
    if invalid_uncovered:
        raise InputError("selection contains invalid uncovered change indexes")


def _add_reason(target: list[DecisionReason], reason: DecisionReason) -> None:
    key = (reason.code, reason.evidence)
    if all((item.code, item.evidence) != key for item in target):
        target.append(reason)


def decide(
    changeset: ChangeSet,
    selection: Selection,
    candidate_results: list[ContractResult],
    comparisons: list[Comparison],
    policy: dict[str, Any] | None = None,
) -> Decision:
    _validate_inputs(selection, candidate_results, comparisons)
    out_of_range = [index for index in selection.uncovered_changes if index >= len(changeset.changes)]
    if out_of_range:
        raise InputError("selection references uncovered change indexes outside the changeset")
    effective = validate_policy(policy)
    block_reasons: list[DecisionReason] = []
    review_reasons: list[DecisionReason] = []

    if not selection.selected_ids and effective["review_on_empty_selection"]:
        _add_reason(
            review_reasons,
            DecisionReason(
                "NO_CONTRACTS_SELECTED",
                "no behavioral contracts were selected; release evidence is insufficient",
                ("selection:selected_ids",),
            ),
        )

    for item in candidate_results:
        if item.risk is not Risk.CRITICAL:
            continue
        if item.status is ResultStatus.MISSING:
            reason = DecisionReason(
                "CRITICAL_TRACE_MISSING",
                f"critical contract {item.contract_id} has no candidate trace",
                (f"results:{item.contract_id}",),
            )
            _add_reason(
                block_reasons if effective["block_on_missing_critical"] else review_reasons,
                reason,
            )
        elif item.status is ResultStatus.FAIL:
            reason = DecisionReason(
                "CRITICAL_CONTRACT_FAILED",
                f"critical contract {item.contract_id} failed",
                (f"results:{item.contract_id}",),
            )
            _add_reason(
                block_reasons if effective["block_on_any_critical_failure"] else review_reasons,
                reason,
            )

    if effective["block_on_new_critical_regression"]:
        for comparison in comparisons:
            if comparison.risk is Risk.CRITICAL and comparison.classification in {
                "new_regression",
                "candidate_missing",
                "newly_covered_failure",
            }:
                _add_reason(
                    block_reasons,
                    DecisionReason(
                        "NEW_CRITICAL_REGRESSION",
                        f"critical behavior regressed: {comparison.contract_id}",
                        (f"comparison:{comparison.contract_id}",),
                    ),
                )

    uncovered_high = [
        changeset.changes[index]
        for index in selection.uncovered_changes
        if changeset.changes[index].severity.rank >= Severity.HIGH.rank
    ]
    if uncovered_high and effective["review_on_uncovered_high_change"]:
        _add_reason(
            review_reasons,
            DecisionReason(
                "UNCOVERED_HIGH_IMPACT_CHANGE",
                f"{len(uncovered_high)} high-impact change(s) have no direct contract coverage",
                tuple(f"change:{change.path}" for change in uncovered_high),
            ),
        )

    high_capability_changes = [
        change
        for change in changeset.changes
        if change.severity.rank >= Severity.HIGH.rank and (change.tool or change.capability)
    ]
    if high_capability_changes and effective["review_on_high_risk_capability_change"]:
        _add_reason(
            review_reasons,
            DecisionReason(
                "HIGH_RISK_CAPABILITY_CHANGED",
                f"{len(high_capability_changes)} high-risk tool or capability change(s) require review",
                tuple(f"change:{change.path}" for change in high_capability_changes),
            ),
        )

    if selection.fallback_applied and effective["review_on_fallback"]:
        _add_reason(
            review_reasons,
            DecisionReason(
                "FAIL_SAFE_FALLBACK_APPLIED",
                "contract selection expanded because impact analysis was incomplete",
                ("selection:fallback",),
            ),
        )

    for item in candidate_results:
        if item.risk is Risk.CRITICAL or item.status is ResultStatus.PASS:
            continue
        _add_reason(
            review_reasons,
            DecisionReason(
                "NONCRITICAL_CONTRACT_FAILED",
                f"{item.risk.value} contract {item.contract_id} is {item.status.value}",
                (f"results:{item.contract_id}",),
            ),
        )

    if block_reasons:
        status = DecisionStatus.BLOCK
        reasons = tuple(block_reasons + review_reasons)
    elif review_reasons:
        status = DecisionStatus.REVIEW
        reasons = tuple(review_reasons)
    else:
        status = DecisionStatus.PASS
        reasons = (
            DecisionReason(
                "EVIDENCE_SATISFIES_POLICY",
                "all selected contracts satisfy the configured release policy",
                ("decision:summary",),
            ),
        )

    summary = {
        "changes": len(changeset.changes),
        "highest_change_severity": changeset.highest_severity.value,
        "selected_contracts": len(selection.selected_ids),
        "total_contracts": selection.total_contracts,
        "selection_reduction_ratio": selection.reduction_ratio,
        "candidate_passed": sum(item.status is ResultStatus.PASS for item in candidate_results),
        "candidate_failed": sum(item.status is ResultStatus.FAIL for item in candidate_results),
        "candidate_missing": sum(item.status is ResultStatus.MISSING for item in candidate_results),
        "critical_selected": sum(item.risk is Risk.CRITICAL for item in candidate_results),
        "new_regressions": sum(item.classification == "new_regression" for item in comparisons),
        "fixed": sum(item.classification == "fixed" for item in comparisons),
    }
    return Decision(status, reasons, summary)
