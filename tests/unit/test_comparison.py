from __future__ import annotations

import pytest

from proofdiff.domain.models import ContractResult, ResultStatus, Risk
from proofdiff.engine.comparison import compare_results


def result(identifier: str, status: ResultStatus) -> ContractResult:
    return ContractResult(identifier, Risk.HIGH, status, (), {})


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (ResultStatus.PASS, ResultStatus.FAIL, "new_regression"),
        (ResultStatus.PASS, ResultStatus.MISSING, "candidate_missing"),
        (ResultStatus.FAIL, ResultStatus.PASS, "fixed"),
        (ResultStatus.FAIL, ResultStatus.FAIL, "persistent_failure"),
        (ResultStatus.MISSING, ResultStatus.PASS, "newly_covered_pass"),
        (ResultStatus.MISSING, ResultStatus.FAIL, "newly_covered_failure"),
        (ResultStatus.PASS, ResultStatus.PASS, "unchanged"),
        (ResultStatus.FAIL, ResultStatus.MISSING, "changed"),
    ],
)
def test_comparison_classifications(
    before: ResultStatus, after: ResultStatus, expected: str
) -> None:
    comparison = compare_results([result("x", before)], [result("x", after)])[0]
    assert comparison.classification == expected


def test_comparison_handles_one_sided_results() -> None:
    assert compare_results([], [result("x", ResultStatus.PASS)])[0].baseline is ResultStatus.MISSING
    assert compare_results([result("x", ResultStatus.FAIL)], [])[0].candidate is ResultStatus.MISSING
