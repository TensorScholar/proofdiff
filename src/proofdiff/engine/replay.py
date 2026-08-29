from __future__ import annotations

from collections import Counter

from proofdiff.domain.models import (
    AssertionResult,
    Contract,
    ContractResult,
    ResultStatus,
    TraceRecord,
)


def _subsequence(expected: tuple[str, ...], actual: list[str]) -> bool:
    if not expected:
        return True
    cursor = 0
    for item in actual:
        if item == expected[cursor]:
            cursor += 1
            if cursor == len(expected):
                return True
    return False


def evaluate_contract(contract: Contract, trace: TraceRecord | None) -> ContractResult:
    if trace is None:
        return ContractResult(
            contract_id=contract.id,
            risk=contract.risk,
            status=ResultStatus.MISSING,
            assertions=(AssertionResult("trace_present", False, "candidate trace is missing"),),
            metrics={},
        )

    assertions: list[AssertionResult] = []
    tokens = [event.token for event in trace.events]
    tool_calls = [event.name for event in trace.events if event.type == "tool_call" and event.name]
    counts = Counter(tool_calls)

    expected_sequence = contract.expectations.required_sequence
    if expected_sequence:
        passed = _subsequence(expected_sequence, tokens)
        assertions.append(
            AssertionResult(
                "required_sequence",
                passed,
                (
                    "sequence observed"
                    if passed
                    else f"expected subsequence {list(expected_sequence)!r}; observed {tokens!r}"
                ),
            )
        )

    for tool in contract.expectations.forbidden_tools:
        passed = counts[tool] == 0
        assertions.append(
            AssertionResult(
                f"forbidden_tool:{tool}",
                passed,
                "tool not called" if passed else f"tool called {counts[tool]} time(s)",
            )
        )

    for tool in contract.expectations.required_tools:
        passed = counts[tool] > 0
        assertions.append(
            AssertionResult(
                f"required_tool:{tool}",
                passed,
                f"tool called {counts[tool]} time(s)" if passed else "tool was not called",
            )
        )

    for tool, maximum in contract.expectations.max_tool_calls.items():
        passed = counts[tool] <= maximum
        assertions.append(
            AssertionResult(
                f"max_tool_calls:{tool}",
                passed,
                f"observed {counts[tool]}, maximum {maximum}",
            )
        )

    output_lower = trace.output.lower()
    for fragment in contract.expectations.output_contains:
        passed = fragment.lower() in output_lower
        assertions.append(
            AssertionResult(
                f"output_contains:{fragment}",
                passed,
                "fragment present" if passed else "fragment absent",
            )
        )
    for fragment in contract.expectations.output_not_contains:
        passed = fragment.lower() not in output_lower
        assertions.append(
            AssertionResult(
                f"output_not_contains:{fragment}",
                passed,
                "fragment absent" if passed else "forbidden fragment present",
            )
        )

    if contract.expectations.output_min_length > 0:
        actual_length = len(trace.output.strip())
        minimum = contract.expectations.output_min_length
        passed = actual_length >= minimum
        assertions.append(
            AssertionResult(
                "output_min_length",
                passed,
                f"observed {actual_length} characters, minimum {minimum}",
            )
        )

    for metric, maximum in contract.expectations.budgets.items():
        actual = trace.metrics.get(metric)
        passed = actual is not None and actual <= maximum
        assertions.append(
            AssertionResult(
                f"budget:{metric}",
                passed,
                f"observed {actual!r}, maximum {maximum}",
            )
        )

    if not assertions:
        assertions.append(
            AssertionResult(
                "contract_has_assertions",
                False,
                "contract defines no executable expectations",
            )
        )
    status = ResultStatus.PASS if all(item.passed for item in assertions) else ResultStatus.FAIL
    return ContractResult(contract.id, contract.risk, status, tuple(assertions), trace.metrics)


def evaluate_selected(
    contracts: list[Contract], selected_ids: tuple[str, ...], traces: dict[str, TraceRecord]
) -> list[ContractResult]:
    by_id = {contract.id: contract for contract in contracts}
    return [evaluate_contract(by_id[identifier], traces.get(identifier)) for identifier in selected_ids]
