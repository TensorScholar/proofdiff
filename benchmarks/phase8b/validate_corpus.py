from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "benchmarks" / "phase8b" / "corpus.json"
SCHEMA_PATH = ROOT / "schemas" / "phase8b-corpus.schema.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_OBSERVATION_KEYS = {
    "baseline_results",
    "big_decision",
    "big_selection",
    "candidate_decision",
    "candidate_result",
    "candidate_selection",
    "evaluation_result",
    "observed_result",
    "selection_result",
}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _walk_keys(value: Any, *, prefix: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            found.append((child_path, key))
            found.extend(_walk_keys(child, prefix=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_keys(child, prefix=f"{prefix}[{index}]"))
    return found


def _schema_errors(
    corpus: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )
    errors: list[str] = []
    schema_errors = sorted(
        validator.iter_errors(corpus),
        key=lambda item: list(item.absolute_path),
    )
    for error in schema_errors:
        location = "$"
        for part in error.absolute_path:
            location += f"[{part}]" if isinstance(part, int) else f".{part}"
        errors.append(f"schema {location}: {error.message}")
    return errors


def _qualified_historical(case: dict[str, Any]) -> bool:
    return case.get("arm") == "historical" and case.get("eligibility") == "qualified"


def _integrity_errors(
    corpus: dict[str, Any],
    *,
    require_freeze_ready: bool,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    cases = corpus.get("cases", [])
    if not isinstance(cases, list):
        return ["cases must be a list"], warnings

    ids: set[str] = set()
    revision_pairs: set[tuple[str, str]] = set()
    family_members: dict[str, list[str]] = defaultdict(list)
    historical_repos: set[str] = set()
    qualified_historical = 0
    controls = 0

    for case in cases:
        if not isinstance(case, dict):
            continue

        case_id = case.get("case_id")
        if not isinstance(case_id, str):
            continue
        if case_id in ids:
            errors.append(f"duplicate case_id: {case_id}")
        ids.add(case_id)

        arm = case.get("arm")
        eligibility = case.get("eligibility")
        repo = case.get("repo")
        base_sha = case.get("base_sha")
        head_sha = case.get("head_sha")
        source_kind = case.get("source_kind")
        source_url = case.get("source_url")
        family_id = case.get("family_id")

        if isinstance(family_id, str):
            family_members[family_id].append(case_id)

        if _qualified_historical(case):
            qualified_historical += 1
            if isinstance(repo, str):
                historical_repos.add(repo)
            if source_kind != "upstream_commit":
                errors.append(
                    f"{case_id}: qualified historical case must use "
                    "source_kind=upstream_commit"
                )
            for label, sha in (("base_sha", base_sha), ("head_sha", head_sha)):
                if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
                    errors.append(
                        f"{case_id}: qualified historical {label} must be a 40-hex SHA"
                    )
            if isinstance(base_sha, str) and isinstance(head_sha, str):
                if base_sha == head_sha:
                    errors.append(f"{case_id}: base_sha and head_sha must differ")
                pair = (repo if isinstance(repo, str) else "", head_sha)
                if pair in revision_pairs:
                    errors.append(
                        f"{case_id}: duplicate qualified historical repo/head pair {pair}"
                    )
                revision_pairs.add(pair)
                if isinstance(source_url, str) and head_sha not in source_url:
                    errors.append(
                        f"{case_id}: source_url must pin the qualified historical head_sha"
                    )

        if arm == "control":
            controls += 1
            if eligibility != "control":
                errors.append(f"{case_id}: control arm must use eligibility=control")
            if not isinstance(base_sha, str) or SHA_RE.fullmatch(base_sha) is None:
                errors.append(f"{case_id}: control base_sha must be frozen")
            if not isinstance(head_sha, str) or SHA_RE.fullmatch(head_sha) is None:
                errors.append(f"{case_id}: control head_sha must be frozen")

        if arm in {"hold", "prospective", "rejected"} and eligibility == "qualified":
            errors.append(f"{case_id}: {arm} arm cannot be qualified")

    for path, key in _walk_keys(corpus):
        if key in FORBIDDEN_OBSERVATION_KEYS:
            errors.append(
                "post-observation field is forbidden before experiment execution: "
                f"{path}"
            )

    qualified_ids = {
        case.get("case_id")
        for case in cases
        if isinstance(case, dict) and _qualified_historical(case)
    }
    for family_id, members in sorted(family_members.items()):
        qualified_members = [
            case_id for case_id in members if case_id in qualified_ids
        ]
        if len(qualified_members) > 2:
            warnings.append(
                f"correlated family {family_id!r} has {len(qualified_members)} "
                "qualified historical cases; report family-stratified results and "
                "do not treat them as independent wins"
            )

    targets = corpus.get("targets", {})
    target_historical = (
        targets.get("new_historical_cases") if isinstance(targets, dict) else None
    )
    target_repos = (
        targets.get("minimum_repositories") if isinstance(targets, dict) else None
    )
    target_controls = targets.get("control_cases") if isinstance(targets, dict) else None

    strict = require_freeze_ready or corpus.get("corpus_status") in {
        "frozen",
        "amended",
    }
    if strict:
        if not isinstance(target_historical, int) or qualified_historical < target_historical:
            errors.append(
                f"freeze gate: {qualified_historical} qualified new historical cases; "
                f"target is {target_historical}"
            )
        if not isinstance(target_repos, int) or len(historical_repos) < target_repos:
            errors.append(
                f"freeze gate: {len(historical_repos)} historical repositories; "
                f"target is {target_repos}"
            )
        if not isinstance(target_controls, int) or controls < target_controls:
            errors.append(
                f"freeze gate: {controls} controls; target is {target_controls}"
            )

    status = corpus.get("corpus_status")
    frozen_at = corpus.get("frozen_at")
    if status == "draft" and frozen_at is not None:
        errors.append("draft corpus must not set frozen_at")
    if status in {"frozen", "amended"} and not isinstance(frozen_at, str):
        errors.append(f"{status} corpus must set frozen_at")

    return errors, warnings


def _summary(corpus: dict[str, Any]) -> str:
    cases = [
        case for case in corpus.get("cases", []) if isinstance(case, dict)
    ]
    arm_counts = Counter(str(case.get("arm")) for case in cases)
    qualified = [case for case in cases if _qualified_historical(case)]
    repo_counts = Counter(str(case.get("repo")) for case in qualified)
    arms = ", ".join(
        f"{key}:{value}" for key, value in sorted(arm_counts.items())
    )
    repositories = ", ".join(
        f"{key}:{value}" for key, value in sorted(repo_counts.items())
    )
    return "\n".join(
        [
            f"corpus_status={corpus.get('corpus_status')}",
            f"experiment_status={corpus.get('experiment_status')}",
            f"arms={arms}",
            f"qualified_historical={len(qualified)}",
            f"qualified_repositories={repositories}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the frozen/draft Phase 8B external corpus."
    )
    parser.add_argument(
        "--require-freeze-ready",
        action="store_true",
        help=(
            "Enforce the numerical/diversity freeze gates even while "
            "corpus_status is draft."
        ),
    )
    args = parser.parse_args()

    try:
        corpus = _load_json(CORPUS_PATH)
        schema = _load_json(SCHEMA_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"phase8b corpus load failed: {exc}", file=sys.stderr)
        return 2

    errors = _schema_errors(corpus, schema)
    integrity_errors, warnings = _integrity_errors(
        corpus,
        require_freeze_ready=args.require_freeze_ready,
    )
    errors.extend(integrity_errors)

    print(_summary(corpus))
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("phase8b corpus validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
