from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from proofdiff.domain.errors import InputError
from proofdiff.domain.models import (
    ChangeType,
    Contract,
    ContractCoverage,
    Expectations,
    Risk,
)
from proofdiff.engine.io import load_object

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
TOP_LEVEL_KEYS = {"id", "title", "risk", "tags", "always_run", "covers", "expect"}
COVERAGE_KEYS = {"tools", "change_types", "manifest_paths", "capabilities"}
EXPECTATION_KEYS = {
    "required_sequence",
    "forbidden_tools",
    "required_tools",
    "max_tool_calls",
    "output_contains",
    "output_not_contains",
    "output_min_length",
    "budgets",
}


def _reject_unknown(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise InputError(f"{field} contains unknown fields: {', '.join(unknown)}")


def _strings(
    value: Any,
    field: str,
    *,
    unique: bool = True,
    trimmed: bool = True,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InputError(f"{field} must be an array of non-empty strings")
    result: list[str] = []
    for item in value:
        invalid = not isinstance(item, str) or not item
        if trimmed and isinstance(item, str):
            invalid = invalid or item != item.strip()
        if invalid:
            qualifier = "trimmed " if trimmed else ""
            raise InputError(f"{field} must be an array of {qualifier}non-empty strings")
        result.append(item)
    if unique and len(set(result)) != len(result):
        raise InputError(f"{field} must not contain duplicates")
    return tuple(result)


def _mapping_ints(value: Any, field: str) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    result: dict[str, int] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or key != key.strip()
            or not isinstance(item, int)
            or isinstance(item, bool)
            or item < 0
        ):
            raise InputError(f"{field} entries must map trimmed strings to non-negative integers")
        result[key] = item
    return result


def _mapping_numbers(value: Any, field: str) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    result: dict[str, float] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not key
            or key != key.strip()
            or not isinstance(item, int | float)
            or isinstance(item, bool)
        ):
            raise InputError(f"{field} entries must map strings to numbers; keys must be trimmed and values finite")
        number = float(item)
        if not math.isfinite(number) or number < 0:
            raise InputError(f"{field} values must be finite and non-negative")
        result[key] = number
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputError(f"{field} must be a non-negative integer")
    return value


def _strict_bool(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InputError(f"{field} must be a boolean")
    return value


def parse_contract(value: dict[str, Any], source: str) -> Contract:
    _reject_unknown(value, TOP_LEVEL_KEYS, source)
    identifier = value.get("id")
    title = value.get("title", identifier)
    if not isinstance(identifier, str) or IDENTIFIER.fullmatch(identifier) is None:
        raise InputError(f"contract id must match {IDENTIFIER.pattern!r}: {source}")
    if not isinstance(title, str) or not title.strip() or title != title.strip():
        raise InputError(f"contract title must be a trimmed non-empty string: {source}")
    try:
        risk = Risk(str(value.get("risk", "medium")))
    except ValueError as exc:
        raise InputError(f"invalid contract risk in {source}") from exc

    coverage_raw = value.get("covers", {})
    expectations_raw = value.get("expect", {})
    if not isinstance(coverage_raw, dict) or not isinstance(expectations_raw, dict):
        raise InputError(f"covers and expect must be objects: {source}")
    _reject_unknown(coverage_raw, COVERAGE_KEYS, f"{source}.covers")
    _reject_unknown(expectations_raw, EXPECTATION_KEYS, f"{source}.expect")

    change_types: list[ChangeType] = []
    for item in _strings(coverage_raw.get("change_types"), f"{source}.covers.change_types"):
        try:
            change_types.append(ChangeType(item))
        except ValueError as exc:
            raise InputError(f"unknown change type {item!r} in {source}") from exc

    expectations = Expectations(
        required_sequence=_strings(
            expectations_raw.get("required_sequence"),
            f"{source}.expect.required_sequence",
            unique=False,
        ),
        forbidden_tools=_strings(
            expectations_raw.get("forbidden_tools"),
            f"{source}.expect.forbidden_tools",
        ),
        required_tools=_strings(
            expectations_raw.get("required_tools"),
            f"{source}.expect.required_tools",
        ),
        max_tool_calls=_mapping_ints(
            expectations_raw.get("max_tool_calls"),
            f"{source}.expect.max_tool_calls",
        ),
        output_contains=_strings(
            expectations_raw.get("output_contains"),
            f"{source}.expect.output_contains",
            trimmed=False,
        ),
        output_not_contains=_strings(
            expectations_raw.get("output_not_contains"),
            f"{source}.expect.output_not_contains",
            trimmed=False,
        ),
        output_min_length=_nonnegative_int(
            expectations_raw.get("output_min_length"),
            f"{source}.expect.output_min_length",
        ),
        budgets=_mapping_numbers(
            expectations_raw.get("budgets"),
            f"{source}.expect.budgets",
        ),
    )
    conflicting_tools = sorted(set(expectations.required_tools) & set(expectations.forbidden_tools))
    if conflicting_tools:
        raise InputError(f"contract requires and forbids the same tools in {source}: {', '.join(conflicting_tools)}")
    impossible_required = sorted(
        tool for tool in expectations.required_tools if expectations.max_tool_calls.get(tool) == 0
    )
    if impossible_required:
        raise InputError(f"required tools have a zero call budget in {source}: {', '.join(impossible_required)}")
    conflicting_fragments = sorted(
        set(item.casefold() for item in expectations.output_contains)
        & set(item.casefold() for item in expectations.output_not_contains)
    )
    if conflicting_fragments:
        raise InputError(f"contract both requires and forbids output fragments in {source}")

    contract = Contract(
        id=identifier,
        title=title,
        risk=risk,
        tags=_strings(value.get("tags"), f"{source}.tags"),
        always_run=_strict_bool(value.get("always_run"), f"{source}.always_run"),
        coverage=ContractCoverage(
            tools=_strings(coverage_raw.get("tools"), f"{source}.covers.tools"),
            change_types=tuple(change_types),
            manifest_paths=_strings(
                coverage_raw.get("manifest_paths"),
                f"{source}.covers.manifest_paths",
            ),
            capabilities=_strings(
                coverage_raw.get("capabilities"),
                f"{source}.covers.capabilities",
            ),
        ),
        expectations=expectations,
        source=source,
    )
    if not any(
        (
            contract.always_run,
            contract.coverage.tools,
            contract.coverage.change_types,
            contract.coverage.manifest_paths,
            contract.coverage.capabilities,
        )
    ):
        raise InputError(f"contract has no coverage declaration: {source}")
    if not any(
        (
            expectations.required_sequence,
            expectations.forbidden_tools,
            expectations.required_tools,
            expectations.max_tool_calls,
            expectations.output_contains,
            expectations.output_not_contains,
            expectations.output_min_length > 0,
            expectations.budgets,
        )
    ):
        raise InputError(f"contract has no executable expectations: {source}")
    return contract


def load_contract(path: str | Path) -> Contract:
    source = Path(path)
    return parse_contract(load_object(source), str(source))


def load_contracts(directory: str | Path) -> list[Contract]:
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise InputError(f"contracts directory does not exist or is unsafe: {root}")
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in {".json", ".yaml", ".yml"}
    )
    contracts = [load_contract(path) for path in paths]
    identifiers: set[str] = set()
    for contract in contracts:
        if contract.id in identifiers:
            raise InputError(f"duplicate contract id: {contract.id}")
        identifiers.add(contract.id)
    if not contracts:
        raise InputError(f"no contracts found in: {root}")
    return contracts
