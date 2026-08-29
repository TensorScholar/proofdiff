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


def test_policy_can_demote_missing_critical_to_review() -> None:
    result = ContractResult("critical", Risk.CRITICAL, ResultStatus.MISSING, (), {})
    decision = decide(
        ChangeSet("a", "b", ()),
        Selection(("critical",), (), (), False, 1),
        [result],
        [],
        {"block_on_missing_critical": False},
    )
    assert decision.status is DecisionStatus.REVIEW


def test_new_critical_regression_blocks_even_without_failed_result_list() -> None:
    comparison = Comparison(
        "critical",
        ResultStatus.PASS,
        ResultStatus.FAIL,
        "new_regression",
        Risk.CRITICAL,
    )
    decision = decide(
        ChangeSet("a", "b", ()),
        Selection(("critical",), (), (), False, 1),
        [],
        [comparison],
    )
    assert decision.status is DecisionStatus.BLOCK


def test_uncovered_high_and_fallback_require_review() -> None:
    change = Change(ChangeType.UNCLASSIFIED_CHANGE, "x", Severity.HIGH, "unknown")
    decision = decide(
        ChangeSet("a", "b", (change,)),
        Selection(("high",), (), (0,), True, 2),
        [ContractResult("high", Risk.HIGH, ResultStatus.PASS, (), {})],
        [],
    )
    assert decision.status is DecisionStatus.REVIEW
    codes = {reason.code for reason in decision.reasons}
    assert "UNCOVERED_HIGH_IMPACT_CHANGE" in codes
    assert "FAIL_SAFE_FALLBACK_APPLIED" in codes
