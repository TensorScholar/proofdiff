from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proofdiff._version import __version__
from proofdiff.domain.errors import InputError, VerificationError
from proofdiff.domain.models import (
    ChangeSet,
    Comparison,
    Contract,
    ContractResult,
    Decision,
    Selection,
    TraceRecord,
)
from proofdiff.engine.canonical import digest
from proofdiff.engine.comparison import compare_results
from proofdiff.engine.decision import decide, validate_policy
from proofdiff.engine.diff import compare_manifests
from proofdiff.engine.io import write_json, write_jsonl
from proofdiff.engine.manifest import validate_manifest
from proofdiff.engine.replay import evaluate_selected
from proofdiff.engine.selector import select_contracts

CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_EVIDENCE_FILES = {
    "baseline-manifest.json",
    "candidate-manifest.json",
    "changeset.json",
    "selection.json",
    "selected-contracts.jsonl",
    "baseline-results.jsonl",
    "candidate-results.jsonl",
    "comparisons.jsonl",
    "trace-digests.json",
    "policy.json",
    "decision.json",
    "claims.json",
    "provenance.json",
    "report.md",
}


@dataclass(frozen=True)
class EvidenceInputs:
    baseline_manifest: dict[str, Any]
    candidate_manifest: dict[str, Any]
    changeset: ChangeSet
    selection: Selection
    baseline_results: list[ContractResult]
    candidate_results: list[ContractResult]
    comparisons: list[Comparison]
    decision: Decision
    contracts: list[Contract] = field(default_factory=list)
    baseline_traces: dict[str, TraceRecord] = field(default_factory=dict)
    candidate_traces: dict[str, TraceRecord] = field(default_factory=dict)
    policy: dict[str, bool] = field(default_factory=dict)




def _validate_evidence_inputs(inputs: EvidenceInputs) -> None:
    protected_baseline = validate_manifest(inputs.baseline_manifest)
    protected_candidate = validate_manifest(inputs.candidate_manifest)
    if protected_baseline != inputs.baseline_manifest:
        raise InputError("baseline manifest is not normalized or contains unprotected secret values")
    if protected_candidate != inputs.candidate_manifest:
        raise InputError("candidate manifest is not normalized or contains unprotected secret values")

    expected_changeset = compare_manifests(protected_baseline, protected_candidate)
    if inputs.changeset != expected_changeset:
        raise InputError("changeset does not match the supplied manifests")

    contract_ids = [item.id for item in inputs.contracts]
    if len(set(contract_ids)) != len(contract_ids):
        raise InputError("evidence contracts contain duplicate ids")
    expected_selection = select_contracts(expected_changeset, inputs.contracts)
    if inputs.selection != expected_selection:
        raise InputError("selection does not match the changeset and supplied contracts")

    expected_baseline_results = evaluate_selected(
        inputs.contracts,
        expected_selection.selected_ids,
        inputs.baseline_traces,
    )
    expected_candidate_results = evaluate_selected(
        inputs.contracts,
        expected_selection.selected_ids,
        inputs.candidate_traces,
    )
    if inputs.baseline_results != expected_baseline_results:
        raise InputError("baseline results do not match the selected contracts and traces")
    if inputs.candidate_results != expected_candidate_results:
        raise InputError("candidate results do not match the selected contracts and traces")

    expected_comparisons = compare_results(expected_baseline_results, expected_candidate_results)
    if inputs.comparisons != expected_comparisons:
        raise InputError("comparisons do not match the baseline and candidate results")

    effective_policy = validate_policy(inputs.policy)
    if inputs.policy != effective_policy:
        raise InputError("evidence policy must contain the complete effective decision policy")
    expected_decision = decide(
        expected_changeset,
        expected_selection,
        expected_candidate_results,
        expected_comparisons,
        effective_policy,
    )
    if inputs.decision != expected_decision:
        raise InputError("decision does not match the supplied evidence and effective policy")


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        try:
            if component.is_symlink():
                raise InputError(f"evidence path contains a symbolic-link component: {component}")
        except OSError as exc:
            raise InputError(f"cannot inspect evidence path component: {component}") from exc


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _claim(inputs: EvidenceInputs) -> dict[str, Any]:
    critical = [item for item in inputs.candidate_results if item.risk.value == "critical"]
    passed_critical = bool(critical) and all(item.passed for item in critical)
    return {
        "claim": "Release decision was computed from scoped behavioral evidence",
        "decision": inputs.decision.status.value,
        "scope": {
            "baseline_digest": digest(inputs.baseline_manifest),
            "candidate_digest": digest(inputs.candidate_manifest),
            "selected_contracts": len(inputs.selection.selected_ids),
            "total_contracts": inputs.selection.total_contracts,
            "fixture_replay": True,
            "critical_contracts_selected": len(critical),
            "critical_contracts_passed": passed_critical,
        },
        "evidence": [
            "changeset.json",
            "selection.json",
            "selected-contracts.jsonl",
            "baseline-results.jsonl",
            "candidate-results.jsonl",
            "comparisons.jsonl",
            "trace-digests.json",
            "policy.json",
            "decision.json",
        ],
        "limitations": [
            "The bundle evaluates supplied traces; it does not prove future live-provider behavior.",
            "Impact-based selection only covers relationships declared by contracts and recognized manifest changes.",
            "Checksums establish integrity after generation, not publisher identity or authenticity.",
            "ProofDiff is not a runtime authorization or credential enforcement system.",
        ],
    }


def _trace_digests(inputs: EvidenceInputs) -> dict[str, Any]:
    selected = inputs.selection.selected_ids
    return {
        "algorithm": "sha256-canonical-json",
        "baseline": {
            case_id: digest(inputs.baseline_traces[case_id].to_dict())
            for case_id in selected
            if case_id in inputs.baseline_traces
        },
        "candidate": {
            case_id: digest(inputs.candidate_traces[case_id].to_dict())
            for case_id in selected
            if case_id in inputs.candidate_traces
        },
        "missing_baseline": [case_id for case_id in selected if case_id not in inputs.baseline_traces],
        "missing_candidate": [case_id for case_id in selected if case_id not in inputs.candidate_traces],
    }


def _write_bundle(root: Path, inputs: EvidenceInputs, report_markdown: str) -> None:
    selected = set(inputs.selection.selected_ids)
    selected_contracts = [contract for contract in inputs.contracts if contract.id in selected]
    write_json(root / "baseline-manifest.json", inputs.baseline_manifest)
    write_json(root / "candidate-manifest.json", inputs.candidate_manifest)
    write_json(root / "changeset.json", inputs.changeset.to_dict())
    write_json(root / "selection.json", inputs.selection.to_dict())
    write_jsonl(root / "selected-contracts.jsonl", [item.to_dict() for item in selected_contracts])
    write_jsonl(root / "baseline-results.jsonl", [item.to_dict() for item in inputs.baseline_results])
    write_jsonl(root / "candidate-results.jsonl", [item.to_dict() for item in inputs.candidate_results])
    write_jsonl(root / "comparisons.jsonl", [item.to_dict() for item in inputs.comparisons])
    write_json(root / "trace-digests.json", _trace_digests(inputs))
    write_json(root / "policy.json", inputs.policy)
    write_json(root / "decision.json", inputs.decision.to_dict())
    write_json(root / "claims.json", _claim(inputs))
    write_json(
        root / "provenance.json",
        {
            "proofdiff_version": __version__,
            "generated_at": datetime.now(UTC).isoformat(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "baseline_digest": digest(inputs.baseline_manifest),
            "candidate_digest": digest(inputs.candidate_manifest),
            "policy_digest": digest(inputs.policy),
            "selected_contracts_digest": digest([item.to_dict() for item in selected_contracts]),
        },
    )
    (root / "report.md").write_text(report_markdown.rstrip() + "\n", encoding="utf-8")

    actual = {path.name for path in root.iterdir() if path.is_file()}
    if actual != REQUIRED_EVIDENCE_FILES:
        raise InputError("internal evidence generation produced an unexpected file set")
    lines = [f"{_sha256_file(root / name)}  {name}" for name in sorted(actual)]
    (root / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_evidence_bundle(destination: str | Path, inputs: EvidenceInputs, report_markdown: str) -> Path:
    _validate_evidence_inputs(inputs)
    root = Path(destination)
    parent = root.parent
    parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(parent)
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise InputError(f"evidence destination is not a safe directory: {root}")
        if any(root.iterdir()):
            raise InputError(f"evidence destination must be empty: {root}")
        root.rmdir()

    temporary = Path(tempfile.mkdtemp(prefix=f".{root.name}.", dir=parent))
    try:
        _write_bundle(temporary, inputs, report_markdown)
        os.replace(temporary, root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return root


def verify_evidence_bundle(destination: str | Path) -> list[str]:
    root = Path(destination)
    if not root.is_dir() or root.is_symlink():
        raise VerificationError("evidence destination must be a regular directory")
    entries = list(root.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise VerificationError("evidence bundle must contain only regular files")

    checksum_path = root / "checksums.txt"
    if not checksum_path.is_file():
        raise VerificationError("checksums.txt is missing")
    verified: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise VerificationError(f"invalid checksum line {line_number}")
        expected, relative = parts
        if CHECKSUM_RE.fullmatch(expected) is None:
            raise VerificationError(f"invalid sha256 digest on line {line_number}")
        if (
            not relative
            or relative in {".", "..", "checksums.txt"}
            or "/" in relative
            or "\\" in relative
        ):
            raise VerificationError(f"unsafe evidence path on line {line_number}")
        if relative in seen:
            raise VerificationError(f"duplicate checksum entry: {relative}")
        seen.add(relative)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise VerificationError(f"evidence file is missing or unsafe: {relative}")
        actual = _sha256_file(path)
        if actual != expected:
            raise VerificationError(f"checksum mismatch: {relative}")
        verified.append(relative)

    if not seen:
        raise VerificationError("checksums.txt contains no entries")

    if seen != REQUIRED_EVIDENCE_FILES:
        missing = sorted(REQUIRED_EVIDENCE_FILES - seen)
        unexpected = sorted(seen - REQUIRED_EVIDENCE_FILES)
        detail = []
        if missing:
            detail.append(f"missing required entries: {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected entries: {', '.join(unexpected)}")
        raise VerificationError("; ".join(detail))

    actual_files = {path.name for path in entries}
    expected_files = REQUIRED_EVIDENCE_FILES | {"checksums.txt"}
    if actual_files != expected_files:
        unexpected = sorted(actual_files - expected_files)
        missing = sorted(expected_files - actual_files)
        detail = []
        if missing:
            detail.append(f"missing files: {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected files: {', '.join(unexpected)}")
        raise VerificationError("; ".join(detail))
    return verified
