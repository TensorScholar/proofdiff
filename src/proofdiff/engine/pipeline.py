from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proofdiff.domain.models import Decision
from proofdiff.engine.comparison import compare_results
from proofdiff.engine.contracts import load_contracts
from proofdiff.engine.decision import decide, validate_policy
from proofdiff.engine.diff import compare_manifests
from proofdiff.engine.evidence import EvidenceInputs, write_evidence_bundle
from proofdiff.engine.io import load_object
from proofdiff.engine.manifest import unwrap_snapshot
from proofdiff.engine.replay import evaluate_selected
from proofdiff.engine.selector import select_contracts
from proofdiff.engine.traces import load_traces
from proofdiff.reporting import render_console, render_markdown


@dataclass(frozen=True)
class CheckRequest:
    baseline_manifest: Path
    candidate_manifest: Path
    contracts_dir: Path
    baseline_traces: Path
    candidate_traces: Path
    evidence_dir: Path
    policy_file: Path | None = None


@dataclass(frozen=True)
class CheckOutcome:
    decision: Decision
    console: str
    evidence_dir: Path


def _read_manifest(path: Path) -> dict[str, Any]:
    return unwrap_snapshot(load_object(path))


def run_check(request: CheckRequest) -> CheckOutcome:
    baseline = _read_manifest(request.baseline_manifest)
    candidate = _read_manifest(request.candidate_manifest)
    contracts = load_contracts(request.contracts_dir)
    changeset = compare_manifests(baseline, candidate)
    selection = select_contracts(changeset, contracts)
    baseline_traces = load_traces(request.baseline_traces)
    candidate_traces = load_traces(request.candidate_traces)
    baseline_results = evaluate_selected(contracts, selection.selected_ids, baseline_traces)
    candidate_results = evaluate_selected(contracts, selection.selected_ids, candidate_traces)
    comparisons = compare_results(baseline_results, candidate_results)
    policy = validate_policy(load_object(request.policy_file) if request.policy_file else None)
    decision = decide(changeset, selection, candidate_results, comparisons, policy)
    markdown = render_markdown(changeset, selection, candidate_results, comparisons, decision)
    console = render_console(changeset, selection, candidate_results, comparisons, decision)
    evidence = write_evidence_bundle(
        request.evidence_dir,
        EvidenceInputs(
            baseline_manifest=baseline,
            candidate_manifest=candidate,
            contracts=contracts,
            changeset=changeset,
            selection=selection,
            baseline_traces=baseline_traces,
            candidate_traces=candidate_traces,
            baseline_results=baseline_results,
            candidate_results=candidate_results,
            comparisons=comparisons,
            policy=policy,
            decision=decision,
        ),
        markdown,
    )
    return CheckOutcome(decision, console, evidence)
