from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from proofdiff.domain.errors import InputError, VerificationError
from proofdiff.domain.models import (
    ChangeSet,
    Contract,
    ContractCoverage,
    Decision,
    DecisionReason,
    DecisionStatus,
    Expectations,
    Risk,
    TraceEvent,
    TraceRecord,
)
from proofdiff.engine.canonical import digest
from proofdiff.engine.comparison import compare_results
from proofdiff.engine.decision import decide, validate_policy
from proofdiff.engine.diff import compare_manifests
from proofdiff.engine.evidence import EvidenceInputs, verify_evidence_bundle, write_evidence_bundle
from proofdiff.engine.io import load_jsonl, load_object
from proofdiff.engine.replay import evaluate_selected
from proofdiff.engine.selector import select_contracts


def _inputs() -> EvidenceInputs:
    baseline = {"agent": {"name": "a"}, "runtime": {"model": "m1"}, "tools": []}
    candidate = {"agent": {"name": "a"}, "runtime": {"model": "m2"}, "tools": []}
    contract = Contract(
        "contract.one",
        "Contract one",
        Risk.CRITICAL,
        ("smoke",),
        True,
        ContractCoverage(manifest_paths=("runtime",)),
        Expectations(output_min_length=1),
        "contract.json",
    )
    trace = TraceRecord(
        "contract.one",
        (TraceEvent("assistant_message", content="ok"),),
        "ok",
        {"latency_ms": 1.0},
    )
    contracts = [contract]
    traces = {"contract.one": trace}
    changeset = compare_manifests(baseline, candidate)
    selection = select_contracts(changeset, contracts)
    baseline_results = evaluate_selected(contracts, selection.selected_ids, traces)
    candidate_results = evaluate_selected(contracts, selection.selected_ids, traces)
    comparisons = compare_results(baseline_results, candidate_results)
    policy = validate_policy(None)
    decision = decide(changeset, selection, candidate_results, comparisons, policy)
    return EvidenceInputs(
        baseline_manifest=baseline,
        candidate_manifest=candidate,
        changeset=changeset,
        selection=selection,
        baseline_results=baseline_results,
        candidate_results=candidate_results,
        comparisons=comparisons,
        decision=decision,
        contracts=contracts,
        baseline_traces=traces,
        candidate_traces=traces,
        policy=policy,
    )


def _rewrite_checksums(root: Path) -> None:
    names = sorted(path.name for path in root.iterdir() if path.is_file() and path.name != "checksums.txt")
    lines = []
    for name in names:
        value = hashlib.sha256((root / name).read_bytes()).hexdigest()
        lines.append(f"{value}  {name}")
    (root / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_bundle_contains_selected_contract_policy_trace_and_provenance_evidence(tmp_path: Path) -> None:
    root = write_evidence_bundle(tmp_path / "evidence", _inputs(), "# Review\n")
    assert len(verify_evidence_bundle(root)) == 14
    assert load_jsonl(root / "selected-contracts.jsonl")[0]["id"] == "contract.one"
    assert load_object(root / "policy.json") == validate_policy(None)
    trace_digests = load_object(root / "trace-digests.json")
    assert trace_digests["missing_baseline"] == []
    assert trace_digests["missing_candidate"] == []
    assert set(trace_digests["baseline"]) == {"contract.one"}
    provenance = load_object(root / "provenance.json")
    assert provenance["baseline_digest"] == _inputs().changeset.baseline_digest
    assert provenance["policy_digest"] == digest(_inputs().policy)


def test_generation_rejects_inconsistent_or_incomplete_evidence(tmp_path: Path) -> None:
    inputs = _inputs()
    with pytest.raises(InputError, match="changeset does not match"):
        write_evidence_bundle(
            tmp_path / "bad-digest",
            replace(inputs, changeset=ChangeSet("0" * 64, inputs.changeset.candidate_digest, ())),
            "# Report",
        )
    with pytest.raises(InputError, match="selection does not match"):
        write_evidence_bundle(tmp_path / "missing-contract", replace(inputs, contracts=[]), "# Report")
    with pytest.raises(InputError, match="candidate results do not match"):
        write_evidence_bundle(tmp_path / "missing-result", replace(inputs, candidate_results=[]), "# Report")
    with pytest.raises(InputError, match="duplicate ids"):
        write_evidence_bundle(
            tmp_path / "duplicate-contract",
            replace(inputs, contracts=[inputs.contracts[0], inputs.contracts[0]]),
            "# Report",
        )
    with pytest.raises(InputError, match="comparisons do not match"):
        write_evidence_bundle(
            tmp_path / "forged-comparison",
            replace(inputs, comparisons=[]),
            "# Report",
        )
    forged_decision = Decision(
        DecisionStatus.BLOCK,
        (DecisionReason("FORGED", "not derived from the evidence"),),
        {},
    )
    with pytest.raises(InputError, match="decision does not match"):
        write_evidence_bundle(
            tmp_path / "forged-decision",
            replace(inputs, decision=forged_decision),
            "# Report",
        )
    with pytest.raises(InputError, match="complete effective"):
        write_evidence_bundle(
            tmp_path / "partial-policy",
            replace(inputs, policy={"block_on_missing_critical": True}),
            "# Report",
        )
    with pytest.raises(InputError, match="policy"):
        write_evidence_bundle(
            tmp_path / "bad-policy",
            replace(inputs, policy={"block": 1}),  # type: ignore[dict-item]
            "# Report",
        )

    raw_secret_manifest = dict(inputs.baseline_manifest)
    raw_secret_manifest["runtime"] = {"model": "m1", "api_token": "plaintext"}
    with pytest.raises(InputError, match="unprotected secret"):
        write_evidence_bundle(
            tmp_path / "raw-secret",
            replace(inputs, baseline_manifest=raw_secret_manifest),
            "# Report",
        )


def test_generation_refuses_nonempty_file_and_symlink_destinations(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "existing.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(InputError, match="must be empty"):
        write_evidence_bundle(occupied, _inputs(), "# Report")

    regular_file = tmp_path / "file"
    regular_file.write_text("x", encoding="utf-8")
    with pytest.raises(InputError, match="not a safe directory"):
        write_evidence_bundle(regular_file, _inputs(), "# Report")

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(InputError, match="not a safe directory"):
        write_evidence_bundle(link, _inputs(), "# Report")
    with pytest.raises(InputError, match="symbolic-link component"):
        write_evidence_bundle(link / "nested-evidence", _inputs(), "# Report")


def test_verifier_rejects_duplicate_unsafe_missing_unexpected_and_nonregular_entries(
    tmp_path: Path,
) -> None:
    root = write_evidence_bundle(tmp_path / "evidence", _inputs(), "# Report")
    original = (root / "checksums.txt").read_text(encoding="utf-8")
    first = original.splitlines()[0]

    (root / "checksums.txt").write_text(original + first + "\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="duplicate checksum"):
        verify_evidence_bundle(root)

    (root / "checksums.txt").write_text("0" * 64 + "  ../escape\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="unsafe evidence path"):
        verify_evidence_bundle(root)

    (root / "checksums.txt").write_text("z" * 64 + "  decision.json\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="invalid sha256"):
        verify_evidence_bundle(root)

    (root / "checksums.txt").write_text(original, encoding="utf-8")
    (root / "decision.json").unlink()
    with pytest.raises(VerificationError, match="missing or unsafe"):
        verify_evidence_bundle(root)

    root = write_evidence_bundle(tmp_path / "evidence-2", _inputs(), "# Report")
    (root / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(VerificationError, match="unexpected files"):
        verify_evidence_bundle(root)

    (root / "unexpected.txt").unlink()
    (root / "nested").mkdir()
    with pytest.raises(VerificationError, match="only regular files"):
        verify_evidence_bundle(root)


def test_verifier_rejects_checksum_set_that_is_valid_but_incomplete_or_expanded(tmp_path: Path) -> None:
    root = write_evidence_bundle(tmp_path / "evidence", _inputs(), "# Report")
    (root / "claims.json").unlink()
    _rewrite_checksums(root)
    with pytest.raises(VerificationError, match="missing required entries"):
        verify_evidence_bundle(root)

    root = write_evidence_bundle(tmp_path / "evidence-2", _inputs(), "# Report")
    extra = root / "extra.json"
    extra.write_text("{}\n", encoding="utf-8")
    _rewrite_checksums(root)
    with pytest.raises(VerificationError, match="unexpected entries"):
        verify_evidence_bundle(root)
