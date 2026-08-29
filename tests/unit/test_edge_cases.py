from __future__ import annotations

from pathlib import Path

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.domain.models import (
    Change,
    ChangeSet,
    ChangeType,
    Contract,
    ContractCoverage,
    Expectations,
    Risk,
    Severity,
    TraceEvent,
    TraceRecord,
)
from proofdiff.engine.canonical import normalize
from proofdiff.engine.contracts import load_contracts, parse_contract
from proofdiff.engine.io import load_document
from proofdiff.engine.replay import evaluate_contract
from proofdiff.engine.selector import select_contracts


def test_canonical_rejects_unsupported_type_and_excessive_depth() -> None:
    with pytest.raises(InputError, match="unsupported value type"):
        normalize((1, 2))
    nested: object = None
    for _ in range(66):
        nested = {"x": nested}
    with pytest.raises(InputError, match="nesting exceeds"):
        normalize(nested)


def test_yaml_load_and_missing_file_errors(tmp_path: Path) -> None:
    path = tmp_path / "value.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    assert load_document(path) == {"a": 1}
    with pytest.raises(InputError, match="cannot stat"):
        load_document(tmp_path / "missing.json")


def test_contract_mapping_and_directory_errors(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="array of non-empty strings"):
        parse_contract(
            {
                "id": "x",
                "covers": {"tools": "bad"},
                "expect": {"output_contains": ["ok"]},
            },
            "memory",
        )
    with pytest.raises(InputError, match="non-negative integers"):
        parse_contract(
            {
                "id": "x",
                "covers": {"tools": ["x"]},
                "expect": {"max_tool_calls": {"x": -1}},
            },
            "memory",
        )
    with pytest.raises(InputError, match="map strings to numbers"):
        parse_contract(
            {
                "id": "x",
                "covers": {"tools": ["x"]},
                "expect": {"budgets": {"cost": "bad"}},
            },
            "memory",
        )
    with pytest.raises(InputError, match="does not exist"):
        load_contracts(tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(InputError, match="no contracts"):
        load_contracts(empty)


def test_selector_matches_change_type_path_and_capability() -> None:
    changes = ChangeSet(
        "a",
        "b",
        (
            Change(
                ChangeType.MODEL_CHANGED,
                "runtime.model",
                Severity.HIGH,
                "model",
                capability="reasoning",
            ),
        ),
    )
    contracts = [
        Contract(
            "type",
            "type",
            Risk.LOW,
            (),
            False,
            ContractCoverage(change_types=(ChangeType.MODEL_CHANGED,)),
            Expectations(output_contains=("ok",)),
            "memory",
        ),
        Contract(
            "path",
            "path",
            Risk.LOW,
            (),
            False,
            ContractCoverage(manifest_paths=("runtime",)),
            Expectations(output_contains=("ok",)),
            "memory",
        ),
        Contract(
            "capability",
            "capability",
            Risk.LOW,
            (),
            False,
            ContractCoverage(capabilities=("reasoning",)),
            Expectations(output_contains=("ok",)),
            "memory",
        ),
    ]
    selected = select_contracts(changes, contracts)
    assert selected.selected_ids == ("capability", "path", "type")


def test_replay_reports_all_failure_modes() -> None:
    contract = Contract(
        "x",
        "x",
        Risk.HIGH,
        (),
        True,
        ContractCoverage(tools=("delete",)),
        Expectations(
            forbidden_tools=("delete",),
            required_tools=("lookup",),
            max_tool_calls={"delete": 0},
            output_contains=("success",),
            output_not_contains=("secret",),
            budgets={"cost": 1.0},
        ),
        "memory",
    )
    trace = TraceRecord(
        "x",
        (TraceEvent("tool_call", "delete"),),
        "secret",
        {"cost": 2.0},
    )
    result = evaluate_contract(contract, trace)
    assert not result.passed
    assert len(result.assertions) == 6
    assert all(not item.passed for item in result.assertions)
