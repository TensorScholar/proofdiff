from __future__ import annotations

from proofdiff.domain.models import Comparison, ContractResult, ResultStatus


def compare_results(baseline: list[ContractResult], candidate: list[ContractResult]) -> list[Comparison]:
    baseline_by_id = {item.contract_id: item for item in baseline}
    candidate_by_id = {item.contract_id: item for item in candidate}
    comparisons: list[Comparison] = []
    for identifier in sorted(set(baseline_by_id) | set(candidate_by_id)):
        before = baseline_by_id.get(identifier)
        after = candidate_by_id.get(identifier)
        baseline_status = before.status if before else ResultStatus.MISSING
        candidate_status = after.status if after else ResultStatus.MISSING
        risk = after.risk if after else before.risk  # type: ignore[union-attr]
        if baseline_status is ResultStatus.PASS and candidate_status is ResultStatus.FAIL:
            classification = "new_regression"
        elif baseline_status is ResultStatus.PASS and candidate_status is ResultStatus.MISSING:
            classification = "candidate_missing"
        elif baseline_status is ResultStatus.FAIL and candidate_status is ResultStatus.PASS:
            classification = "fixed"
        elif baseline_status is ResultStatus.FAIL and candidate_status is ResultStatus.FAIL:
            classification = "persistent_failure"
        elif baseline_status is ResultStatus.MISSING and candidate_status is ResultStatus.PASS:
            classification = "newly_covered_pass"
        elif baseline_status is ResultStatus.MISSING and candidate_status is ResultStatus.FAIL:
            classification = "newly_covered_failure"
        elif baseline_status is candidate_status:
            classification = "unchanged"
        else:
            classification = "changed"
        comparisons.append(Comparison(identifier, baseline_status, candidate_status, classification, risk))
    return comparisons
