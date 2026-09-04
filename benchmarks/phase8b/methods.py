from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proofdiff.domain.models import (
    Change,
    ChangeSet,
    ChangeType,
    Contract,
    ContractCoverage,
    Expectations,
    Risk,
    Severity,
)
from proofdiff.engine.selector import select_contracts

ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = ROOT / "benchmarks" / "phase8b" / "static_rules.json"
RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class MethodResult:
    method_id: str
    selected_ids: tuple[str, ...]
    review: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "selected_ids": list(self.selected_ids),
            "review": self.review,
            "reasons": list(self.reasons),
        }


def load_rules(path: Path = RULES_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Phase 8B static rules must be a JSON object")
    return value


def _risk_at_least(behavior: dict[str, Any], threshold: str) -> bool:
    return RISK_RANK.get(str(behavior.get("risk")), 0) >= RISK_RANK[threshold]


def _critical_ids(behaviors: list[dict[str, Any]]) -> set[str]:
    return {
        str(behavior["behavior_id"])
        for behavior in behaviors
        if str(behavior.get("risk")) == "critical"
    }


def _high_critical_ids(behaviors: list[dict[str, Any]]) -> set[str]:
    return {
        str(behavior["behavior_id"])
        for behavior in behaviors
        if _risk_at_least(behavior, "high")
    }


def _component_tags(repo: str, path: str, rules: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for rule in rules.get("component_rules", {}).get(repo, []):
        prefix = str(rule.get("prefix", ""))
        if prefix and path.startswith(prefix):
            tags.update(str(tag) for tag in rule.get("tags", []))
    return tags


def _path_tags(repo: str, path: str, rules: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for rule in rules.get("path_rules", {}).get(repo, []):
        pattern = str(rule.get("glob", ""))
        if pattern and fnmatch.fnmatchcase(path, pattern):
            tags.update(str(tag) for tag in rule.get("tags", []))
    return tags


def _select_by_tags(
    *,
    method_id: str,
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any],
    tagger: str,
) -> MethodResult:
    selected = _critical_ids(behaviors)
    changed_tags: set[str] = set()
    unknown_paths: list[str] = []

    for path in changed_paths:
        tags = _component_tags(repo, path, rules) if tagger == "component" else _path_tags(repo, path, rules)
        if not tags:
            unknown_paths.append(path)
        changed_tags.update(tags)

    for behavior in behaviors:
        surface_tags = {str(tag) for tag in behavior.get("surface_tags", [])}
        if surface_tags & changed_tags:
            selected.add(str(behavior["behavior_id"]))

    reasons = [f"matched_tags={','.join(sorted(changed_tags))}" if changed_tags else "matched_tags=<none>"]
    review = bool(unknown_paths)
    if review:
        selected.update(_high_critical_ids(behaviors))
        reasons.append(f"unknown_paths={len(unknown_paths)}:widen_high_critical")

    return MethodResult(
        method_id=method_id,
        selected_ids=tuple(sorted(selected)),
        review=review,
        reasons=tuple(reasons),
    )


def full_suite(
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any],
) -> MethodResult:
    del repo, changed_paths, rules
    return MethodResult(
        method_id="full_suite",
        selected_ids=tuple(sorted(str(item["behavior_id"]) for item in behaviors)),
        review=False,
        reasons=("reference_full_suite",),
    )


def static_component_v1(
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any],
) -> MethodResult:
    return _select_by_tags(
        method_id="static_component_v1",
        repo=repo,
        changed_paths=changed_paths,
        behaviors=behaviors,
        rules=rules,
        tagger="component",
    )


def path_rules_v1(
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any],
) -> MethodResult:
    return _select_by_tags(
        method_id="path_rules_v1",
        repo=repo,
        changed_paths=changed_paths,
        behaviors=behaviors,
        rules=rules,
        tagger="path",
    )


def _tokens(value: str) -> set[str]:
    return set(TOKEN_RE.findall(value.lower().replace("_", " ").replace("-", " ")))


def lexical_surface_v1(
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any],
) -> MethodResult:
    policy = rules["lexical_surface"]
    minimum_shared = int(policy["minimum_shared_tokens"])
    minimum_jaccard = float(policy["minimum_jaccard"])

    change_tokens: set[str] = set()
    recognized = False
    for path in changed_paths:
        change_tokens.update(_tokens(path))
        tags = _component_tags(repo, path, rules) | _path_tags(repo, path, rules)
        if tags:
            recognized = True
        for tag in tags:
            change_tokens.update(_tokens(tag))

    selected = _critical_ids(behaviors)
    lexical_hits = 0
    for behavior in behaviors:
        behavior_tokens = _tokens(str(behavior.get("description", "")))
        for tag in behavior.get("surface_tags", []):
            behavior_tokens.update(_tokens(str(tag)))
        shared = change_tokens & behavior_tokens
        union = change_tokens | behavior_tokens
        jaccard = (len(shared) / len(union)) if union else 0.0
        if len(shared) >= minimum_shared and jaccard >= minimum_jaccard:
            selected.add(str(behavior["behavior_id"]))
            lexical_hits += 1

    review = not recognized
    reasons = [f"lexical_hits={lexical_hits}", f"token_count={len(change_tokens)}"]
    if review:
        selected.update(_high_critical_ids(behaviors))
        reasons.append("unrecognized_change_namespace:widen_high_critical")

    return MethodResult(
        method_id="lexical_surface_v1",
        selected_ids=tuple(sorted(selected)),
        review=review,
        reasons=tuple(reasons),
    )


def _risk(value: str) -> Risk:
    return Risk(value)


def proofdiff_v0_1_0(
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any],
) -> MethodResult:
    """Run the released selector through the frozen external-source adapter."""
    contracts = [
        Contract(
            id=str(behavior["behavior_id"]),
            title=str(behavior.get("description", behavior["behavior_id"])),
            risk=_risk(str(behavior.get("risk", "medium"))),
            tags=tuple(sorted(str(tag) for tag in behavior.get("surface_tags", []))),
            always_run=False,
            coverage=ContractCoverage(
                capabilities=tuple(sorted(str(tag) for tag in behavior.get("surface_tags", [])))
            ),
            expectations=Expectations(),
            source="phase8b-derived-behavior-catalog",
        )
        for behavior in behaviors
    ]

    changes: list[Change] = []
    for path in changed_paths:
        tags = _path_tags(repo, path, rules)
        if not tags:
            changes.append(
                Change(
                    type=ChangeType.UNCLASSIFIED_CHANGE,
                    path=path,
                    severity=Severity.HIGH,
                    summary="sanitized external source change",
                )
            )
            continue
        for tag in sorted(tags):
            changes.append(
                Change(
                    type=ChangeType.SOURCE_CODE_CHANGED,
                    path=path,
                    severity=Severity.MEDIUM,
                    summary="sanitized external source change",
                    capability=tag,
                )
            )

    changeset = ChangeSet(
        baseline_digest="phase8b-baseline",
        candidate_digest="phase8b-candidate",
        changes=tuple(changes),
    )
    selection = select_contracts(changeset, contracts)
    review = selection.fallback_applied or bool(selection.uncovered_changes)
    reasons = [
        "released_select_contracts",
        f"fallback={str(selection.fallback_applied).lower()}",
        f"uncovered={len(selection.uncovered_changes)}",
    ]
    return MethodResult(
        method_id="proofdiff_v0_1_0",
        selected_ids=selection.selected_ids,
        review=review,
        reasons=tuple(reasons),
    )


METHODS = {
    "full_suite": full_suite,
    "static_component_v1": static_component_v1,
    "path_rules_v1": path_rules_v1,
    "lexical_surface_v1": lexical_surface_v1,
    "proofdiff_v0_1_0": proofdiff_v0_1_0,
}


def run_method(
    method_id: str,
    *,
    repo: str,
    changed_paths: list[str],
    behaviors: list[dict[str, Any]],
    rules: dict[str, Any] | None = None,
) -> MethodResult:
    try:
        method = METHODS[method_id]
    except KeyError as exc:
        raise ValueError(f"unknown Phase 8B method: {method_id}") from exc
    return method(repo, changed_paths, behaviors, rules or load_rules())
