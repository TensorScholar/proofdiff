from __future__ import annotations

from pathlib import Path

import pytest

from proofdiff.domain.errors import VerificationError
from proofdiff.domain.models import (
    Contract,
    ContractCoverage,
    Expectations,
    Risk,
    TraceRecord,
)
from proofdiff.engine.comparison import compare_results
from proofdiff.engine.decision import decide, validate_policy
from proofdiff.engine.diff import compare_manifests
from proofdiff.engine.evidence import EvidenceInputs, verify_evidence_bundle, write_evidence_bundle
from proofdiff.engine.replay import evaluate_selected
from proofdiff.engine.selector import select_contracts


def inputs() -> EvidenceInputs:
    manifest = {"agent": {"name": "a"}, "runtime": {}, "tools": []}
    contract = Contract(
        "c",
        "critical contract",
        Risk.CRITICAL,
        (),
        True,
        ContractCoverage(manifest_paths=("agent",)),
        Expectations(output_min_length=1),
        "test",
    )
    trace = TraceRecord("c", (), "ok", {})
    contracts = [contract]
    changeset = compare_manifests(manifest, manifest)
    selection = select_contracts(changeset, contracts)
    baseline_results = evaluate_selected(contracts, selection.selected_ids, {"c": trace})
    candidate_results = evaluate_selected(contracts, selection.selected_ids, {"c": trace})
    comparisons = compare_results(baseline_results, candidate_results)
    policy = validate_policy(None)
    decision = decide(changeset, selection, candidate_results, comparisons, policy)
    return EvidenceInputs(
        manifest,
        manifest,
        changeset,
        selection,
        baseline_results,
        candidate_results,
        comparisons,
        decision,
        contracts=contracts,
        baseline_traces={"c": trace},
        candidate_traces={"c": trace},
        policy=policy,
    )


def test_bundle_verifies_and_detects_tampering(tmp_path: Path) -> None:
    root = write_evidence_bundle(tmp_path / "evidence", inputs(), "# Report")
    verified = verify_evidence_bundle(root)
    assert "decision.json" in verified
    (root / "decision.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(VerificationError):
        verify_evidence_bundle(root)
