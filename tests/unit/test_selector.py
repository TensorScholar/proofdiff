from __future__ import annotations

from proofdiff.domain.models import (
    Change,
    ChangeSet,
    ChangeType,
    Contract,
    ContractCoverage,
    Expectations,
    Risk,
    Severity,
)
from proofdiff.engine.selector import select_contracts


def contract(identifier: str, *, risk: Risk, tools: tuple[str, ...] = (), always: bool = False) -> Contract:
    return Contract(
        id=identifier,
        title=identifier,
        risk=risk,
        tags=("smoke",) if always else (),
        always_run=always,
        coverage=ContractCoverage(tools=tools),
        expectations=Expectations(output_contains=("ok",)),
        source="memory",
    )


def test_selects_direct_tool_contract_and_critical() -> None:
    changes = ChangeSet(
        "a",
        "b",
        (Change(ChangeType.TOOL_SCHEMA_CHANGED, "tools.refund", Severity.HIGH, "changed", tool="refund"),),
    )
    selection = select_contracts(
        changes,
        [
            contract("refund", risk=Risk.HIGH, tools=("refund",)),
            contract("critical", risk=Risk.CRITICAL),
            contract("unrelated", risk=Risk.LOW, tools=("search",)),
        ],
    )
    assert selection.selected_ids == ("critical", "refund")
    assert selection.uncovered_changes == ()


def test_uncovered_high_change_applies_fallback() -> None:
    changes = ChangeSet(
        "a",
        "b",
        (Change(ChangeType.UNCLASSIFIED_CHANGE, "mystery", Severity.HIGH, "changed"),),
    )
    selection = select_contracts(
        changes,
        [contract("high", risk=Risk.HIGH), contract("low", risk=Risk.LOW)],
    )
    assert selection.fallback_applied
    assert selection.selected_ids == ("high",)
    assert selection.uncovered_changes == (0,)
