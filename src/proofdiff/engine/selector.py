from __future__ import annotations

from proofdiff.domain.models import (
    ChangeSet,
    ChangeType,
    Contract,
    Risk,
    Selection,
    SelectionReason,
    Severity,
)


def _matches_path(contract_path: str, changed_path: str) -> bool:
    return (
        changed_path == contract_path
        or changed_path.startswith(contract_path + ".")
        or contract_path.startswith(changed_path + ".")
    )


def select_contracts(changeset: ChangeSet, contracts: list[Contract]) -> Selection:
    reasons_by_id: dict[str, set[str]] = {}
    covered_change_indexes: set[int] = set()

    for contract in contracts:
        reasons: set[str] = set()
        if contract.always_run:
            reasons.add("always_run")
        if contract.risk is Risk.CRITICAL:
            reasons.add("mandatory_critical")
        for index, change in enumerate(changeset.changes):
            matched = False
            if change.tool and change.tool in contract.coverage.tools:
                reasons.add(f"tool:{change.tool}")
                matched = True
            if change.type in contract.coverage.change_types:
                reasons.add(f"change_type:{change.type.value}")
                matched = True
            if change.capability and change.capability in contract.coverage.capabilities:
                reasons.add(f"capability:{change.capability}")
                matched = True
            if any(_matches_path(path, change.path) for path in contract.coverage.manifest_paths):
                reasons.add(f"manifest_path:{change.path}")
                matched = True
            if matched:
                covered_change_indexes.add(index)
        if reasons:
            reasons_by_id[contract.id] = reasons

    uncovered = [index for index in range(len(changeset.changes)) if index not in covered_change_indexes]
    fallback = any(
        changeset.changes[index].type is ChangeType.UNCLASSIFIED_CHANGE
        or changeset.changes[index].severity.rank >= Severity.HIGH.rank
        for index in uncovered
    )
    if fallback:
        for contract in contracts:
            if contract.risk in {Risk.CRITICAL, Risk.HIGH} or "smoke" in contract.tags:
                reasons_by_id.setdefault(contract.id, set()).add("fail_safe_fallback")

    selected = tuple(sorted(reasons_by_id))
    reasons = tuple(
        SelectionReason(contract_id=contract_id, reasons=tuple(sorted(reasons_by_id[contract_id])))
        for contract_id in selected
    )
    return Selection(
        selected_ids=selected,
        reasons=reasons,
        uncovered_changes=tuple(uncovered),
        fallback_applied=fallback,
        total_contracts=len(contracts),
    )
