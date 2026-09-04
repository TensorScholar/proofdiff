from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.phase8b.harness import (  # noqa: E402
    assert_candidate_payload_no_leakage,
    candidate_case_envelope,
    derive_behavior_catalog,
    derive_ground_truth,
    is_candidate_source_path,
)
from benchmarks.phase8b.methods import METHODS, load_rules, run_method  # noqa: E402

GATE_PATH = ROOT / "benchmarks" / "phase8b" / "gate_b.json"
CORPUS_PATH = ROOT / "benchmarks" / "phase8b" / "corpus.json"
SCHEMA_PATH = ROOT / "schemas" / "phase8b-gate-b.schema.json"
EXPECTED_METHODS = {
    "full_suite",
    "static_component_v1",
    "path_rules_v1",
    "lexical_surface_v1",
    "proofdiff_v0_1_0",
}
FORBIDDEN_RESULT_KEYS = {
    "baseline_results",
    "big_result",
    "big_selection",
    "candidate_result",
    "candidate_selection",
    "observed_result",
    "score_result",
    "winner",
}
HEX40 = re.compile(r"\b[0-9a-f]{40}\b")
PR_REF = re.compile(r"(?:pull/|pr[_ -]?number|#)\s*\d+", flags=re.IGNORECASE)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode()
    return hashlib.sha1(header + raw, usedforsecurity=False).hexdigest()


def _walk_keys(value: Any, prefix: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}"
            found.append((child_path, str(key)))
            found.extend(_walk_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_keys(child, f"{prefix}[{index}]"))
    return found


def _schema_errors(gate: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(gate), key=lambda item: list(item.absolute_path)):
        location = "$"
        for part in error.absolute_path:
            location += f"[{part}]" if isinstance(part, int) else f".{part}"
        errors.append(f"schema {location}: {error.message}")
    return errors


def _qualified(case: dict[str, Any]) -> bool:
    return case.get("arm") == "historical" and case.get("eligibility") == "qualified"


def _rules_integrity(
    rules: dict[str, Any],
    corpus: dict[str, Any],
    *,
    require_freeze_ready: bool,
    gate_status: str,
) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []
    rules_status = rules.get("rules_status")
    if rules_status not in {"draft", "frozen", "amended"}:
        errors.append("static_rules.rules_status must be draft, frozen, or amended")
    if gate_status in {"frozen", "amended"} and rules_status not in {"frozen", "amended"}:
        errors.append("frozen/amended Gate B requires frozen/amended static rules")

    qualified = [case for case in corpus.get("cases", []) if isinstance(case, dict) and _qualified(case)]
    repos = {str(case.get("repo")) for case in qualified}
    component_rules = rules.get("component_rules")
    path_rules = rules.get("path_rules")
    if not isinstance(component_rules, dict) or not isinstance(path_rules, dict):
        return ["static rules must define component_rules and path_rules objects"], warnings, 0

    for repo in sorted(repos):
        if not component_rules.get(repo):
            errors.append(f"missing component rules for qualified repository {repo}")
        if not path_rules.get(repo):
            errors.append(f"missing path rules for qualified repository {repo}")

    forbidden_tokens = {
        str(case.get("case_id"))
        for case in corpus.get("cases", [])
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    for case in corpus.get("cases", []):
        if not isinstance(case, dict):
            continue
        for key in ("base_sha", "head_sha"):
            value = case.get(key)
            if isinstance(value, str):
                forbidden_tokens.add(value)

    manual_entries = 0
    known_behavior_tags: dict[str, set[str]] = {}
    catalogs = derive_behavior_catalog(corpus)
    for repo, behaviors in catalogs.items():
        known_behavior_tags[repo] = {
            str(tag)
            for behavior in behaviors
            for tag in behavior.get("surface_tags", [])
            if isinstance(tag, str)
        }

    for section_name, section in (("component_rules", component_rules), ("path_rules", path_rules)):
        for repo, entries in section.items():
            if not isinstance(entries, list):
                errors.append(f"{section_name}.{repo} must be a list")
                continue
            for index, entry in enumerate(entries):
                manual_entries += 1
                if not isinstance(entry, dict):
                    errors.append(f"{section_name}.{repo}[{index}] must be an object")
                    continue
                locator_key = "prefix" if section_name == "component_rules" else "glob"
                locator = entry.get(locator_key)
                tags = entry.get("tags")
                if not isinstance(locator, str) or not locator:
                    errors.append(f"{section_name}.{repo}[{index}] missing non-empty {locator_key}")
                if not isinstance(tags, list) or not tags or len(tags) != len(set(tags)):
                    errors.append(f"{section_name}.{repo}[{index}] tags must be non-empty and unique")
                    continue
                unknown_tags = sorted(set(str(tag) for tag in tags) - known_behavior_tags.get(repo, set()))
                if unknown_tags:
                    warnings.append(
                        f"{section_name}.{repo}[{index}] contains tags absent from current behavior catalog: "
                        + ", ".join(unknown_tags)
                    )

    serialized = json.dumps(rules, sort_keys=True)
    for token in sorted(forbidden_tokens):
        if token and token in serialized:
            errors.append(f"static rules contain case-specific frozen token: {token}")
    if "oracle" in serialized.lower() or "case_id" in serialized.lower():
        errors.append("static rules may not contain oracle or case_id mappings")
    if HEX40.search(serialized):
        errors.append("static rules may not contain 40-hex commit identifiers")
    if PR_REF.search(serialized):
        errors.append("static rules may not contain PR/case-number mappings")

    lexical = rules.get("lexical_surface")
    if not isinstance(lexical, dict):
        errors.append("static rules must define lexical_surface policy")
    else:
        if lexical.get("minimum_shared_tokens") != 1:
            errors.append("lexical minimum_shared_tokens must remain frozen at 1")
        if lexical.get("minimum_jaccard") != 0.08:
            errors.append("lexical minimum_jaccard must remain frozen at 0.08")
        if lexical.get("unknown_policy") != "widen_or_review":
            errors.append("lexical unknown_policy must remain widen_or_review")

    if require_freeze_ready and manual_entries < 20:
        errors.append("freeze gate: strong static baselines require at least 20 explicit reusable mapping entries")
    return errors, warnings, manual_entries


def _method_smoke_errors(corpus: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rules = load_rules()
    repo = "pydantic/pydantic-ai"
    behaviors = [
        {
            "behavior_id": "critical_behavior",
            "repo": repo,
            "description": "critical approval behavior",
            "surface_tags": ["approvals"],
            "risk": "critical",
        },
        {
            "behavior_id": "provider_behavior",
            "repo": repo,
            "description": "provider adapter streaming behavior",
            "surface_tags": ["provider-adapter", "streaming"],
            "risk": "high",
        },
        {
            "behavior_id": "memory_behavior",
            "repo": repo,
            "description": "unrelated memory behavior",
            "surface_tags": ["memory"],
            "risk": "medium",
        },
    ]
    changed = ["pydantic_ai_slim/pydantic_ai/models/xai.py"]

    full = run_method("full_suite", repo=repo, changed_paths=changed, behaviors=behaviors, rules=rules)
    if set(full.selected_ids) != {"critical_behavior", "provider_behavior", "memory_behavior"}:
        errors.append("full_suite smoke check did not select every behavior")

    for method_id in EXPECTED_METHODS - {"full_suite"}:
        result = run_method(method_id, repo=repo, changed_paths=changed, behaviors=behaviors, rules=rules)
        if "critical_behavior" not in result.selected_ids:
            errors.append(f"{method_id} smoke check failed mandatory critical selection")

    unknown = run_method(
        "path_rules_v1",
        repo=repo,
        changed_paths=["pydantic_ai_slim/pydantic_ai/unknown_new_surface.py"],
        behaviors=behaviors,
        rules=rules,
    )
    if not unknown.review or "provider_behavior" not in unknown.selected_ids:
        errors.append("path_rules_v1 unknown-path smoke check must REVIEW and widen high/critical")

    # The catalog/ground-truth split itself must remain internally complete.
    catalogs = derive_behavior_catalog(corpus)
    truth = derive_ground_truth(corpus)
    for row in truth:
        repo_catalog = {item["behavior_id"] for item in catalogs.get(str(row["repo"]), [])}
        missing = set(row["behavior_ids"]) - repo_catalog
        if missing:
            errors.append(f"ground truth references behavior IDs absent from candidate catalog: {sorted(missing)}")
    return errors


def _integrity_errors(
    gate: dict[str, Any],
    corpus: dict[str, Any],
    rules: dict[str, Any],
    *,
    require_freeze_ready: bool,
) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []

    for path, key in _walk_keys(gate):
        if key in FORBIDDEN_RESULT_KEYS:
            errors.append(f"post-observation result key forbidden before candidate execution: {path}")

    status = str(gate.get("gate_status"))
    frozen_at = gate.get("frozen_at")
    if status == "draft" and frozen_at is not None:
        errors.append("draft Gate B must not set frozen_at")
    if status in {"frozen", "amended"} and not isinstance(frozen_at, str):
        errors.append(f"{status} Gate B must set frozen_at")

    if corpus.get("corpus_status") not in {"frozen", "amended"}:
        errors.append("Gate B requires a frozen/amended Phase 8B corpus")
    if corpus.get("experiment_status") not in {"preregistering", "ready"}:
        errors.append("Gate B may only be frozen before experiment execution")

    anchor = gate.get("corpus_anchor")
    if isinstance(anchor, dict):
        observed_blob = _git_blob_sha(CORPUS_PATH)
        if anchor.get("git_blob_sha") != observed_blob:
            errors.append(
                "corpus anchor mismatch: Gate B is not bound to the exact current corpus bytes "
                f"({anchor.get('git_blob_sha')} != {observed_blob})"
            )

    artifacts = gate.get("artifacts")
    if isinstance(artifacts, dict):
        for label, relative in artifacts.items():
            if not isinstance(relative, str) or not (ROOT / relative).is_file():
                errors.append(f"missing Gate B artifact {label}: {relative}")

    methods = gate.get("methods")
    method_ids = [item.get("id") for item in methods if isinstance(item, dict)] if isinstance(methods, list) else []
    if len(method_ids) != len(set(method_ids)):
        errors.append("Gate B method IDs must be unique")
    if set(method_ids) != EXPECTED_METHODS:
        errors.append(f"Gate B methods must be exactly {sorted(EXPECTED_METHODS)}")
    if set(METHODS) != EXPECTED_METHODS:
        errors.append("implemented baseline method registry does not match preregistered method set")

    anti = gate.get("anti_leakage")
    if isinstance(anti, dict):
        visible = set(str(item) for item in anti.get("candidate_visible", []))
        evaluator = set(str(item) for item in anti.get("evaluator_only", []))
        overlap = sorted(visible & evaluator)
        if overlap:
            errors.append(f"candidate-visible/evaluator-only fields overlap: {overlap}")
        if anti.get("candidate_network_access") is not False:
            errors.append("candidate network access must be false")
        if anti.get("candidate_benchmark_repo_access") is not False:
            errors.append("candidate benchmark-repo access must be false")
        if anti.get("candidate_git_metadata_access") is not False:
            errors.append("candidate git-metadata access must be false")

    qualified_cases = [case for case in corpus.get("cases", []) if isinstance(case, dict) and _qualified(case)]
    if qualified_cases:
        envelope = candidate_case_envelope(qualified_cases[0])
        envelope["behavior_catalog"] = derive_behavior_catalog(corpus).get(str(qualified_cases[0]["repo"]), [])
        try:
            assert_candidate_payload_no_leakage(envelope)
        except ValueError as exc:
            errors.append(str(exc))

    if is_candidate_source_path("tests/test_secret_oracle.py"):
        errors.append("source sanitizer must reject tests")
    if is_candidate_source_path("docs/reproducer.md"):
        errors.append("source sanitizer must reject docs")
    if not is_candidate_source_path("src/package/runtime.py"):
        errors.append("source sanitizer must retain ordinary production source")

    rule_errors, rule_warnings, manual_entries = _rules_integrity(
        rules,
        corpus,
        require_freeze_ready=require_freeze_ready,
        gate_status=status,
    )
    errors.extend(rule_errors)
    warnings.extend(rule_warnings)
    errors.extend(_method_smoke_errors(corpus))

    if require_freeze_ready:
        scoring = gate.get("scoring", {})
        selectivity = scoring.get("selectivity", {}) if isinstance(scoring, dict) else {}
        if selectivity.get("headline_excess_reduction_vs_strongest_safe_static_min") != 0.25:
            errors.append("freeze gate: headline excess-selection reduction threshold must be 0.25")
        if selectivity.get("minimum_repository_wins") != 3:
            errors.append("freeze gate: minimum_repository_wins must be 3")
        if selectivity.get("minimum_family_wins") != 5:
            errors.append("freeze gate: minimum_family_wins must be 5")

    return errors, warnings, manual_entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 8B Gate B baseline/scoring preregistration.")
    parser.add_argument(
        "--require-freeze-ready",
        action="store_true",
        help="Enforce all Gate B readiness checks even while gate_status/rules_status are draft.",
    )
    args = parser.parse_args()

    try:
        gate = _load_json(GATE_PATH)
        corpus = _load_json(CORPUS_PATH)
        schema = _load_json(SCHEMA_PATH)
        rules = load_rules()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"phase8b Gate B load failed: {exc}", file=sys.stderr)
        return 2

    errors = _schema_errors(gate, schema)
    integrity_errors, warnings, manual_entries = _integrity_errors(
        gate,
        corpus,
        rules,
        require_freeze_ready=args.require_freeze_ready,
    )
    errors.extend(integrity_errors)

    catalogs = derive_behavior_catalog(corpus)
    truth = derive_ground_truth(corpus)
    print(f"gate_status={gate.get('gate_status')}")
    print(f"rules_status={rules.get('rules_status')}")
    print(f"methods={','.join(sorted(EXPECTED_METHODS))}")
    print(f"behavior_catalog_repositories={len(catalogs)}")
    print(f"evaluator_cases={len(truth)}")
    print(f"manual_static_mapping_entries={manual_entries}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("phase8b Gate B validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
