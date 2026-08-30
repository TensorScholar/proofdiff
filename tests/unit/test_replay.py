from __future__ import annotations

from proofdiff.domain.models import (
    Contract,
    ContractCoverage,
    Expectations,
    ResultStatus,
    Risk,
    TraceEvent,
    TraceRecord,
)
from proofdiff.engine.replay import evaluate_contract


def test_evaluates_trajectory_and_budget() -> None:
    contract = Contract(
        id="refund",
        title="refund",
        risk=Risk.CRITICAL,
        tags=(),
        always_run=True,
        coverage=ContractCoverage(tools=("refund",)),
        expectations=Expectations(
            required_sequence=("tool_call:lookup", "approval:refund", "tool_call:refund"),
            max_tool_calls={"refund": 1},
            output_contains=("completed",),
            budgets={"cost_usd": 0.05},
        ),
        source="memory",
    )
    trace = TraceRecord(
        "refund",
        (
            TraceEvent("tool_call", "lookup"),
            TraceEvent("approval", "refund"),
            TraceEvent("tool_call", "refund"),
        ),
        "Completed",
        {"cost_usd": 0.01},
    )
    result = evaluate_contract(contract, trace)
    assert result.status is ResultStatus.PASS
    assert all(item.passed for item in result.assertions)


def test_missing_trace_is_missing() -> None:
    contract = Contract(
        "x",
        "x",
        Risk.HIGH,
        (),
        True,
        ContractCoverage(manifest_paths=("agent",)),
        Expectations(output_contains=("ok",)),
        "memory",
    )
    assert evaluate_contract(contract, None).status is ResultStatus.MISSING
