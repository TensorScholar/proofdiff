from __future__ import annotations

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.domain.models import ChangeType, Risk
from proofdiff.engine.contracts import parse_contract


def test_parse_contract() -> None:
    contract = parse_contract(
        {
            "id": "x",
            "risk": "critical",
            "always_run": True,
            "covers": {"change_types": ["MODEL_CHANGED"]},
            "expect": {"forbidden_tools": ["delete"]},
        },
        "memory",
    )
    assert contract.risk is Risk.CRITICAL
    assert contract.coverage.change_types == (ChangeType.MODEL_CHANGED,)


def test_contract_requires_coverage() -> None:
    with pytest.raises(InputError):
        parse_contract({"id": "x", "risk": "low", "covers": {}, "expect": {}}, "memory")


def test_unknown_change_type_rejected() -> None:
    with pytest.raises(InputError):
        parse_contract(
            {
                "id": "x",
                "covers": {"change_types": ["NOT_REAL"]},
                "expect": {"output_contains": ["ok"]},
            },
            "memory",
        )
