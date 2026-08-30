from __future__ import annotations

import pytest

from proofdiff.domain.errors import InputError
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
from proofdiff.engine.decision import DEFAULT_POLICY, decide, validate_policy


def _selection(ids: tuple[str, ...] = ("c",), *, uncovered: tuple[int, ...] = ()) -> Selection:
    return Selection(ids, (), uncovered, False, max(1, len(ids)))


def test_policy_rejects_wrong_shape_unknown_fields_and_non_booleans() -> None:
    assert validate_policy(None) == DEFAULT_POLICY
    with pytest.raises(InputError, match="must be an object"):
        validate_policy([])  # type: ignore[arg-type]
    with pytest.raises(InputError, match="unknown fields"):
        validate_policy({"permit_everything": True})
    with pytest.raises(InputError, match="must be a boolean"):
        validate_policy({"review_on_fallback": 1})


def test_decision_validates_duplicate_and_unselected_evidence() -> None:
    result = ContractResult("c", Risk.HIGH, ResultStatus.PASS, (), {})
    comparison = Comparison("c", ResultStatus.PASS, ResultStatus.PASS, "unchanged", Risk.HIGH)
    changes = ChangeSet("a", "b", ())

    with pytest.raises(InputError, match="selection contains duplicate"):
        decide(changes, _selection(("c", "c")), [result], [comparison])
    with pytest.raises(InputError, match="candidate results contain duplicate"):
        decide(changes, _selection(), [result, result], [comparison])
    with pytest.raises(InputError, match="unselected contracts"):
        decide(changes, _selection(), [ContractResult("x", Risk.HIGH, ResultStatus.PASS, (), {})], [])
    with pytest.raises(InputError, match="comparisons contain duplicate"):
        decide(changes, _selection(), [result], [comparison, comparison])
    with pytest.raises(InputError, match="comparisons reference unselected"):
        decide(
            changes,
            _selection(),
            [result],
            [Comparison("x", ResultStatus.PASS, ResultStatus.PASS, "unchanged", Risk.HIGH)],
        )


def test_empty_selection_and_noncritical_failure_require_review() -> None:
    empty = decide(ChangeSet("a", "a", ()), Selection((), (), (), False, 0), [], [])
    assert empty.status is DecisionStatus.REVIEW
    assert {reason.code for reason in empty.reasons} == {"NO_CONTRACTS_SELECTED"}

    result = ContractResult("c", Risk.MEDIUM, ResultStatus.MISSING, (), {})
    reviewed = decide(ChangeSet("a", "b", ()), _selection(), [result], [])
    assert reviewed.status is DecisionStatus.REVIEW
    assert "NONCRITICAL_CONTRACT_FAILED" in {reason.code for reason in reviewed.reasons}


def test_critical_failure_and_regression_controls_are_independent() -> None:
    failed = ContractResult("c", Risk.CRITICAL, ResultStatus.FAIL, (), {})
    decision = decide(
        ChangeSet("a", "b", ()),
        _selection(),
        [failed],
        [],
        {"block_on_any_critical_failure": False},
    )
    assert decision.status is DecisionStatus.REVIEW

    for classification in ("new_regression", "candidate_missing", "newly_covered_failure"):
        comparison = Comparison("c", ResultStatus.PASS, ResultStatus.FAIL, classification, Risk.CRITICAL)
        blocked = decide(ChangeSet("a", "b", ()), _selection(), [], [comparison])
        assert blocked.status is DecisionStatus.BLOCK

    demoted = decide(
        ChangeSet("a", "b", ()),
        _selection(),
        [],
        [Comparison("c", ResultStatus.PASS, ResultStatus.FAIL, "new_regression", Risk.CRITICAL)],
        {"block_on_new_critical_regression": False},
    )
    assert demoted.status is DecisionStatus.PASS


def test_policy_can_disable_review_reasons_without_hiding_blockers() -> None:
    change = Change(ChangeType.TOOL_ADDED, "tools.x", Severity.HIGH, "added", tool="x")
    selection = Selection(("c",), (), (0,), True, 1)
    result = ContractResult("c", Risk.CRITICAL, ResultStatus.MISSING, (), {})
    decision = decide(
        ChangeSet("a", "b", (change,)),
        selection,
        [result],
        [],
        {
            "review_on_uncovered_high_change": False,
            "review_on_high_risk_capability_change": False,
            "review_on_fallback": False,
        },
    )
    assert decision.status is DecisionStatus.BLOCK
    assert {reason.code for reason in decision.reasons} == {"CRITICAL_TRACE_MISSING"}
