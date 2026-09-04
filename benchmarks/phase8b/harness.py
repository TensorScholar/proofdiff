from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
FORBIDDEN_CANDIDATE_KEYS = {
    "case_id",
    "family_id",
    "criticality",
    "confounding_risk",
    "protected_invariants",
    "oracle",
    "ground_truth_behavior_ids",
    "source_url",
    "pr_number",
    "upstream_reference",
    "discrimination_reason",
    "notes",
    "title",
}


def normalize_invariant(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).strip()


def behavior_id(repo: str, invariant: str) -> str:
    normalized = normalize_invariant(invariant)
    digest = hashlib.sha256(f"{repo}\0{normalized}".encode()).hexdigest()[:20]
    return f"b_{digest}"


def _catalog_case(case: dict[str, Any]) -> bool:
    return (case.get("arm") == "historical" and case.get("eligibility") == "qualified") or (
        case.get("arm") == "control" and case.get("eligibility") == "control"
    )


def derive_behavior_catalog(corpus: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Derive candidate-visible repo-wide behavior catalogs without case associations."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_case in corpus.get("cases", []):
        if not isinstance(raw_case, dict) or not _catalog_case(raw_case):
            continue
        repo = raw_case.get("repo")
        invariants = raw_case.get("protected_invariants")
        surfaces = raw_case.get("behavior_surfaces")
        risk = raw_case.get("criticality")
        if not isinstance(repo, str) or not isinstance(invariants, list):
            continue
        surface_tags = sorted({str(item) for item in surfaces or [] if isinstance(item, str)})
        risk_value = str(risk)
        for invariant in invariants:
            if not isinstance(invariant, str):
                continue
            normalized = normalize_invariant(invariant)
            key = (repo, normalized)
            current = merged.get(key)
            if current is None:
                merged[key] = {
                    "behavior_id": behavior_id(repo, normalized),
                    "repo": repo,
                    "description": normalized,
                    "surface_tags": surface_tags,
                    "risk": risk_value,
                }
                continue
            current["surface_tags"] = sorted(set(current["surface_tags"]) | set(surface_tags))
            if RISK_RANK.get(risk_value, 0) > RISK_RANK.get(str(current["risk"]), 0):
                current["risk"] = risk_value

    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in merged.values():
        by_repo[str(item["repo"])].append(item)
    return {repo: sorted(items, key=lambda item: str(item["behavior_id"])) for repo, items in sorted(by_repo.items())}


def derive_ground_truth(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive evaluator-only case-to-behavior labels from the frozen corpus."""
    rows: list[dict[str, Any]] = []
    for raw_case in corpus.get("cases", []):
        if not isinstance(raw_case, dict) or not _catalog_case(raw_case):
            continue
        repo = raw_case.get("repo")
        invariants = raw_case.get("protected_invariants")
        if not isinstance(repo, str) or not isinstance(invariants, list):
            continue
        ids = sorted({behavior_id(repo, invariant) for invariant in invariants if isinstance(invariant, str)})
        rows.append(
            {
                "case_id": raw_case.get("case_id"),
                "repo": repo,
                "behavior_ids": ids,
                "criticality": raw_case.get("criticality"),
                "family_id": raw_case.get("family_id"),
                "confounding_risk": raw_case.get("confounding_risk"),
                "arm": raw_case.get("arm"),
            }
        )
    return sorted(rows, key=lambda row: str(row["case_id"]))


def candidate_case_envelope(case: dict[str, Any]) -> dict[str, Any]:
    """Return only immutable identity needed to prepare a candidate input."""
    repo = str(case["repo"])
    base_sha = str(case["base_sha"])
    head_sha = str(case["head_sha"])
    run_key = hashlib.sha256(f"{repo}\0{base_sha}\0{head_sha}".encode()).hexdigest()[:24]
    return {
        "run_key": run_key,
        "repo": repo,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def is_candidate_source_path(path: str) -> bool:
    """Keep production source while removing common oracle/prose surfaces."""
    normalized = path.replace("\\", "/").lstrip("./")
    pure = PurePosixPath(normalized)
    lowered_parts = {part.lower() for part in pure.parts}
    name = pure.name.lower()

    if not normalized or ".git" in lowered_parts or ".github" in lowered_parts:
        return False
    if lowered_parts & {"test", "tests", "docs", "documentation", "examples", "benchmarks"}:
        return False
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith(".snap"):
        return False
    if re.match(r"^(changelog|release)(\.|-|_|$)", name, flags=re.IGNORECASE):
        return False
    return True


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def assert_candidate_payload_no_leakage(payload: dict[str, Any]) -> None:
    leaked = sorted(set(_walk_keys(payload)) & FORBIDDEN_CANDIDATE_KEYS)
    if leaked:
        raise ValueError(f"candidate payload contains evaluator-only keys: {', '.join(leaked)}")
