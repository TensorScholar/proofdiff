from __future__ import annotations

from proofdiff.domain.models import (
    Change,
    ChangeSet,
    ChangeType,
    Comparison,
    ContractResult,
    DecisionStatus,
    ResultStatus,
    Risk,
    Selection,
    Severity,
)
from proofdiff.engine.decision import decide


def selection(*, uncovered: tuple[int, ...] = (), fallback: bool = False) -> Selection:
    return Selection(("c",), (), uncovered, fallback, 1)


def test_critical_failure_blocks() -> None:
    changes = ChangeSet("a", "b", ())
    result = ContractResult("c", Risk.CRITICAL, ResultStatus.FAIL, (), {})
    decision = decide(changes, selection(), [result], [])
    assert decision.status is DecisionStatus.BLOCK


def test_high_capability_change_requires_review_even_when_contract_passes() -> None:
    change = Change(
        ChangeType.TOOL_INPUT_SCHEMA_EXPANDED,
        "tools.refund.input_schema",
        Severity.HIGH,
        "expanded",
        tool="refund",
    )
    changes = ChangeSet("a", "b", (change,))
    result = ContractResult("c", Risk.CRITICAL, ResultStatus.PASS, (), {})
    comparison = Comparison("c", ResultStatus.PASS, ResultStatus.PASS, "unchanged", Risk.CRITICAL)
    decision = decide(changes, selection(), [result], [comparison])
    assert decision.status is DecisionStatus.REVIEW


def test_clean_evidence_passes() -> None:
    changes = ChangeSet("a", "a", ())
    result = ContractResult("c", Risk.CRITICAL, ResultStatus.PASS, (), {})
    comparison = Comparison("c", ResultStatus.PASS, ResultStatus.PASS, "unchanged", Risk.CRITICAL)
    decision = decide(changes, selection(), [result], [comparison])
    assert decision.status is DecisionStatus.PASS
