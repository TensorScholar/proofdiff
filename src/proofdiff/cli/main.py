from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

from proofdiff._version import __version__
from proofdiff.domain.errors import ProofDiffError, VerificationError
from proofdiff.domain.models import DecisionStatus
from proofdiff.engine.contracts import load_contracts
from proofdiff.engine.diff import compare_manifests
from proofdiff.engine.evidence import verify_evidence_bundle
from proofdiff.engine.io import load_object, write_json
from proofdiff.engine.manifest import snapshot_manifest, unwrap_snapshot
from proofdiff.engine.pipeline import CheckRequest, run_check
from proofdiff.engine.selector import select_contracts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proofdiff",
        description="Change-aware release assurance for AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"proofdiff {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a minimal ProofDiff workspace")
    init.add_argument("--directory", default=".")
    init.add_argument("--force", action="store_true")

    snapshot = sub.add_parser("snapshot", help="canonicalize and hash an agent manifest")
    snapshot.add_argument("--manifest", required=True)
    snapshot.add_argument("--out", required=True)

    diff = sub.add_parser("diff", help="compare baseline and candidate manifests")
    diff.add_argument("--baseline", required=True)
    diff.add_argument("--candidate", required=True)
    diff.add_argument("--out")

    select = sub.add_parser("select", help="select contracts affected by a manifest change")
    select.add_argument("--baseline", required=True)
    select.add_argument("--candidate", required=True)
    select.add_argument("--contracts", required=True)
    select.add_argument("--out")

    check = sub.add_parser("check", help="run the complete release-assurance pipeline")
    check.add_argument("--baseline", required=True)
    check.add_argument("--candidate", required=True)
    check.add_argument("--contracts", required=True)
    check.add_argument("--baseline-traces", required=True)
    check.add_argument("--candidate-traces", required=True)
    check.add_argument("--evidence", required=True)
    check.add_argument("--policy")

    verify = sub.add_parser("verify", help="verify an evidence bundle checksum manifest")
    verify.add_argument("--evidence", required=True)

    return parser


def _load_manifest(path: str) -> dict[str, Any]:
    return unwrap_snapshot(load_object(path))


def _init_workspace(directory: Path, force: bool) -> None:
    marker = directory / ".proofdiff"
    contracts = directory / "contracts" / "smoke"
    if marker.exists() and not force:
        raise ProofDiffError(f"workspace already exists: {marker}")
    marker.mkdir(parents=True, exist_ok=True)
    contracts.mkdir(parents=True, exist_ok=True)
    policy = {
        "block_on_missing_critical": True,
        "block_on_new_critical_regression": True,
        "block_on_any_critical_failure": True,
        "review_on_uncovered_high_change": True,
        "review_on_high_risk_capability_change": True,
        "review_on_fallback": True,
    }
    contract = {
        "id": "smoke.agent.responds",
        "title": "Agent produces a response",
        "risk": "critical",
        "tags": ["smoke"],
        "always_run": True,
        "covers": {"manifest_paths": ["agent"]},
        "expect": {"output_min_length": 1},
    }
    write_json(marker / "policy.json", policy)
    write_json(contracts / "agent-responds.json", contract)
    (marker / "README.md").write_text(
        "Run `proofdiff check` with baseline/candidate manifests and traces.\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            target = Path(args.directory).resolve()
            target.mkdir(parents=True, exist_ok=True)
            _init_workspace(target, args.force)
            print(f"ProofDiff workspace created at {target}")
            return 0
        if args.command == "snapshot":
            value = snapshot_manifest(args.manifest, args.out)
            print(value)
            return 0
        if args.command == "diff":
            changeset = compare_manifests(_load_manifest(args.baseline), _load_manifest(args.candidate))
            payload = changeset.to_dict()
            if args.out:
                write_json(args.out, payload)
            else:
                import json

                print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "select":
            changeset = compare_manifests(_load_manifest(args.baseline), _load_manifest(args.candidate))
            selection = select_contracts(changeset, load_contracts(args.contracts))
            payload = selection.to_dict()
            if args.out:
                write_json(args.out, payload)
            else:
                import json

                print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "check":
            outcome = run_check(
                CheckRequest(
                    baseline_manifest=Path(args.baseline),
                    candidate_manifest=Path(args.candidate),
                    contracts_dir=Path(args.contracts),
                    baseline_traces=Path(args.baseline_traces),
                    candidate_traces=Path(args.candidate_traces),
                    evidence_dir=Path(args.evidence),
                    policy_file=Path(args.policy) if args.policy else None,
                )
            )
            print(outcome.console)
            return {
                DecisionStatus.PASS: 0,
                DecisionStatus.REVIEW: 1,
                DecisionStatus.BLOCK: 2,
            }[outcome.decision.status]
        if args.command == "verify":
            verified = verify_evidence_bundle(args.evidence)
            print(f"Verified {len(verified)} evidence files")
            return 0
    except VerificationError as exc:
        print(f"ProofDiff verification error: {exc}", file=sys.stderr)
        return 3
    except (ProofDiffError, OSError) as exc:
        print(f"ProofDiff error: {exc}", file=sys.stderr)
        return 3
    parser.error("unknown command")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
