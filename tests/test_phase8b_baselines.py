from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchmarks.phase8b.harness import (
    assert_candidate_payload_no_leakage,
    behavior_id,
    derive_behavior_catalog,
    derive_ground_truth,
    is_candidate_source_path,
)
from benchmarks.phase8b.methods import load_rules, run_method

ROOT = Path(__file__).parents[1]
CORPUS = json.loads((ROOT / "benchmarks" / "phase8b" / "corpus.json").read_text(encoding="utf-8"))


def test_behavior_id_normalizes_whitespace() -> None:
    first = behavior_id("owner/repo", "A protected   behavior\nremains stable.")
    second = behavior_id("owner/repo", "A protected behavior remains stable.")
    assert first == second


def test_candidate_behavior_catalog_removes_case_association() -> None:
    catalogs = derive_behavior_catalog(CORPUS)
    truth = derive_ground_truth(CORPUS)
    assert catalogs
    assert truth

    visible_keys = {"behavior_id", "repo", "description", "surface_tags", "risk"}
    for behaviors in catalogs.values():
        for behavior in behaviors:
            assert set(behavior) == visible_keys

    for row in truth:
        catalog_ids = {item["behavior_id"] for item in catalogs[row["repo"]]}
        assert set(row["behavior_ids"]) <= catalog_ids


def test_candidate_source_filter_removes_oracle_and_prose_surfaces() -> None:
    assert not is_candidate_source_path("tests/test_regression.py")
    assert not is_candidate_source_path("package/tests/test_regression.py")
    assert not is_candidate_source_path("docs/reproducer.md")
    assert not is_candidate_source_path(".github/workflows/ci.yml")
    assert not is_candidate_source_path("CHANGELOG.md")
    assert is_candidate_source_path("src/package/runtime.py")


def test_candidate_payload_rejects_evaluator_keys() -> None:
    with pytest.raises(ValueError, match="evaluator-only"):
        assert_candidate_payload_no_leakage({"repo": "owner/repo", "oracle": {"tests": ["secret"]}})


def test_strong_static_methods_select_critical_and_match_known_surface() -> None:
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
    rules = load_rules()

    full = run_method("full_suite", repo=repo, changed_paths=changed, behaviors=behaviors, rules=rules)
    assert set(full.selected_ids) == {"critical_behavior", "provider_behavior", "memory_behavior"}

    for method_id in ("static_component_v1", "path_rules_v1", "lexical_surface_v1", "proofdiff_v0_1_0"):
        result = run_method(method_id, repo=repo, changed_paths=changed, behaviors=behaviors, rules=rules)
        assert "critical_behavior" in result.selected_ids
        assert "provider_behavior" in result.selected_ids


def test_unknown_path_widens_instead_of_claiming_safe_skip() -> None:
    repo = "pydantic/pydantic-ai"
    behaviors = [
        {
            "behavior_id": "critical_behavior",
            "repo": repo,
            "description": "critical behavior",
            "surface_tags": ["approvals"],
            "risk": "critical",
        },
        {
            "behavior_id": "high_behavior",
            "repo": repo,
            "description": "high behavior",
            "surface_tags": ["provider-adapter"],
            "risk": "high",
        },
        {
            "behavior_id": "medium_behavior",
            "repo": repo,
            "description": "medium behavior",
            "surface_tags": ["memory"],
            "risk": "medium",
        },
    ]
    result = run_method(
        "path_rules_v1",
        repo=repo,
        changed_paths=["pydantic_ai_slim/pydantic_ai/new_unknown_surface.py"],
        behaviors=behaviors,
        rules=load_rules(),
    )
    assert result.review is True
    assert set(result.selected_ids) == {"critical_behavior", "high_behavior"}
