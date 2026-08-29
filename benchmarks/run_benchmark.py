from __future__ import annotations

import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proofdiff.domain.models import (  # noqa: E402
    Change,
    ChangeSet,
    ChangeType,
    Contract,
    ContractCoverage,
    ContractResult,
    Expectations,
    ResultStatus,
    Risk,
    Severity,
)
from proofdiff.engine.decision import decide  # noqa: E402
from proofdiff.engine.diff import compare_manifests  # noqa: E402
from proofdiff.engine.selector import select_contracts  # noqa: E402

SEED = 20260728
SCENARIOS = 300
CONTRACTS = 2_000
TOOLS = 200


def contract(index: int) -> Contract:
    tool = f"tool_{index % TOOLS}"
    risk = Risk.CRITICAL if index % 50 == 0 else (Risk.HIGH if index % 11 == 0 else Risk.MEDIUM)
    return Contract(
        id=f"contract_{index}",
        title=f"Contract {index}",
        risk=risk,
        tags=("smoke",) if index % 100 == 1 else (),
        always_run=index % 100 == 1,
        coverage=ContractCoverage(tools=(tool,)),
        expectations=Expectations(output_contains=("ok",)),
        source="synthetic",
    )


def manifest(optional_property: str | None = None) -> dict[str, object]:
    properties: dict[str, object] = {"query": {"type": "string"}}
    if optional_property:
        properties[optional_property] = {"type": "string"}
    return {
        "agent": {"name": "benchmark-agent"},
        "runtime": {"provider": "fixture", "model": "recorded"},
        "tools": [
            {
                "name": "tool_0",
                "description": "benchmark tool",
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": ["query"],
                },
            }
        ],
    }


def main() -> int:
    rng = random.Random(SEED)
    contracts = [contract(index) for index in range(CONTRACTS)]
    durations: list[float] = []
    recall_values: list[float] = []
    reduction_values: list[float] = []

    for scenario in range(SCENARIOS):
        tool_index = rng.randrange(TOOLS)
        change = Change(
            ChangeType.TOOL_INPUT_SCHEMA_EXPANDED,
            f"tools.tool_{tool_index}.input_schema",
            Severity.HIGH,
            "synthetic optional property added",
            tool=f"tool_{tool_index}",
            capability=f"tool_{tool_index}",
        )
        changeset = ChangeSet("sha256:baseline", f"sha256:candidate-{scenario}", (change,))
        oracle = {item.id for item in contracts if change.tool in item.coverage.tools}
        started = time.perf_counter()
        selected = select_contracts(changeset, contracts)
        durations.append(time.perf_counter() - started)
        selected_ids = set(selected.selected_ids)
        recall_values.append(1.0 if not oracle else len(oracle & selected_ids) / len(oracle))
        reduction_values.append(selected.reduction_ratio)

    benign_changes = compare_manifests(manifest(), manifest())
    benign_selection = select_contracts(benign_changes, contracts)
    passing = [
        ContractResult(identifier, Risk.CRITICAL, ResultStatus.PASS, (), {})
        for identifier in benign_selection.selected_ids
    ]
    benign_decision = decide(benign_changes, benign_selection, passing, [])

    critical_change = Change(
        ChangeType.POLICY_SCOPE_EXPANDED,
        "policy",
        Severity.CRITICAL,
        "synthetic privilege expansion",
    )
    critical_changeset = ChangeSet("a", "b", (critical_change,))
    critical_selection = select_contracts(critical_changeset, contracts)
    critical_results = [
        ContractResult(identifier, Risk.CRITICAL, ResultStatus.FAIL, (), {})
        for identifier in critical_selection.selected_ids
        if next(item for item in contracts if item.id == identifier).risk is Risk.CRITICAL
    ]
    critical_decision = decide(critical_changeset, critical_selection, critical_results, [])

    result = {
        "benchmark": "proofdiff-maintained-synthetic-change-selection-v1",
        "scope": "synthetic manifests and declared contract coverage; not a production workload claim",
        "seed": SEED,
        "scenarios": SCENARIOS,
        "contracts": CONTRACTS,
        "tools": TOOLS,
        "selection_recall_mean": statistics.fmean(recall_values),
        "selection_recall_min": min(recall_values),
        "suite_reduction_mean": statistics.fmean(reduction_values),
        "selection_latency_ms_median": statistics.median(durations) * 1000,
        "selection_latency_ms_p95": sorted(durations)[int(0.95 * len(durations)) - 1] * 1000,
        "benign_identical_manifest_decision": benign_decision.status.value,
        "injected_critical_failure_decision": critical_decision.status.value,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    output = ROOT / "benchmarks" / "results.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
