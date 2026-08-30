from __future__ import annotations

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.domain.models import Contract, ContractCoverage, Expectations, Risk, TraceRecord
from proofdiff.engine.contracts import parse_contract
from proofdiff.engine.replay import evaluate_contract


def test_output_min_length_is_enforced() -> None:
    contract = Contract(
        "response",
        "response",
        Risk.CRITICAL,
        (),
        True,
        ContractCoverage(manifest_paths=("agent",)),
        Expectations(output_min_length=1),
        "memory",
    )
    result = evaluate_contract(contract, TraceRecord("response", (), "", {}))
    assert not result.passed
    assert result.assertions[0].assertion == "output_min_length"


def test_output_min_length_validation() -> None:
    with pytest.raises(InputError, match="non-negative integer"):
        parse_contract(
            {
                "id": "response",
                "covers": {"manifest_paths": ["agent"]},
                "expect": {"output_min_length": -1},
            },
            "memory",
        )
