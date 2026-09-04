from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
PHASE = ROOT / "benchmarks" / "phase8b"
PROTOCOL_PATH = PHASE / "gate_d.json"

STATIC_METHODS = ["static_component_v1", "path_rules_v1", "lexical_surface_v1"]
REQUIRED_FIRST_OBSERVATION_FIELDS = {
    "protocol_blob_sha",
    "candidate_blob_sha",
    "corpus_blob_sha",
    "gate_b_blob_sha",
    "input_manifest_digest",
    "started_at",
    "completed_at",
    "attempt_history",
    "per_case_direction_candidate_outputs",
    "per_method_raw_outputs",
    "per_case_direction_scores",
    "aggregate_scores",
    "strongest_safe_static_method",
    "gate_results",
    "final_phase8b_decision",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _expect(findings: list[str], condition: bool, message: str) -> None:
    if not condition:
        findings.append(message)


def _locked_file_findings(protocol: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    frozen_inputs = protocol.get("frozen_inputs")
    if not isinstance(frozen_inputs, dict):
        return ["frozen_inputs must be an object"]

    for name in ("corpus", "gate_b", "static_rules", "harness", "methods", "candidate"):
        spec = frozen_inputs.get(name)
        if not isinstance(spec, dict):
            findings.append(f"frozen_inputs.{name} must be an object")
            continue
        relative = spec.get("path")
        expected = spec.get("git_blob_sha")
        if not isinstance(relative, str) or not relative:
            findings.append(f"frozen_inputs.{name}.path must be a non-empty string")
            continue
        if not isinstance(expected, str) or len(expected) != 40:
            findings.append(f"frozen_inputs.{name}.git_blob_sha must be a 40-character Git blob SHA")
            continue
        path = ROOT / relative
        if not path.is_file():
            findings.append(f"locked file is missing: {relative}")
            continue
        actual = _git_blob_sha(path)
        if actual != expected:
            findings.append(f"locked file drifted: {relative}: expected {expected}, got {actual}")
    return findings


def validate_protocol(protocol: dict[str, Any], *, require_freeze_ready: bool) -> list[str]:
    findings = _locked_file_findings(protocol)

    _expect(findings, protocol.get("schema_version") == "1.0", "schema_version must be 1.0")
    _expect(findings, protocol.get("phase") == "8B", "phase must be 8B")
    _expect(findings, protocol.get("gate") == "D", "gate must be D")
    _expect(
        findings,
        protocol.get("protocol_status") in {"draft", "frozen"},
        "protocol_status must be draft or frozen",
    )
    _expect(
        findings,
        protocol.get("observation_state_at_protocol_creation") == "unobserved",
        "protocol must attest that candidate outputs were unobserved at protocol creation",
    )

    status = protocol.get("protocol_status")
    frozen_at = protocol.get("frozen_at")
    if status == "draft":
        _expect(findings, frozen_at is None, "draft protocol must not have frozen_at")
    elif status == "frozen":
        _expect(findings, isinstance(frozen_at, str) and bool(frozen_at), "frozen protocol requires frozen_at")

    frozen_inputs = protocol.get("frozen_inputs", {})
    candidate = frozen_inputs.get("candidate", {}) if isinstance(frozen_inputs, dict) else {}
    _expect(findings, candidate.get("id") == "minimal_big_v1", "candidate id must be minimal_big_v1")
    _expect(
        findings,
        candidate.get("main_merge_sha") == protocol.get("protocol_base_commit"),
        "protocol base commit must equal the Gate C candidate main merge",
    )

    gate_b = _load(PHASE / "gate_b.json")
    corpus = _load(PHASE / "corpus.json")
    static_rules = _load(PHASE / "static_rules.json")

    _expect(findings, gate_b.get("gate_status") == "frozen", "Gate B must remain frozen")
    _expect(findings, static_rules.get("rules_status") == "frozen", "static rules must remain frozen")
    _expect(findings, bool(corpus.get("frozen_at")), "corpus must retain frozen_at provenance")

    if isinstance(frozen_inputs, dict):
        corpus_spec = frozen_inputs.get("corpus", {})
        gate_b_spec = frozen_inputs.get("gate_b", {})
        _expect(
            findings,
            gate_b.get("corpus_anchor", {}).get("git_blob_sha") == corpus_spec.get("git_blob_sha"),
            "Gate D corpus blob must equal the frozen Gate B corpus anchor",
        )
        _expect(
            findings,
            gate_b_spec.get("git_blob_sha") == _git_blob_sha(PHASE / "gate_b.json"),
            "Gate D must lock the current frozen Gate B blob",
        )

    execution = protocol.get("execution_design")
    if not isinstance(execution, dict):
        findings.append("execution_design must be an object")
        execution = {}

    gate_b_experiment = gate_b.get("experimental_unit", {})
    gate_b_anti_leakage = gate_b.get("anti_leakage", {})
    _expect(
        findings,
        execution.get("headline_arm") == gate_b_experiment.get("primary_arm"),
        "headline arm must match frozen Gate B primary arm",
    )
    _expect(
        findings,
        execution.get("controls_in_headline") == gate_b_experiment.get("controls_in_headline"),
        "control headline policy must match frozen Gate B",
    )
    _expect(
        findings,
        execution.get("directions") == gate_b_experiment.get("directions"),
        "directions must match frozen Gate B",
    )
    _expect(
        findings,
        execution.get("candidate_visible_fields") == gate_b_anti_leakage.get("candidate_visible"),
        "candidate-visible fields must exactly match frozen Gate B",
    )
    _expect(
        findings,
        execution.get("evaluator_only_fields") == gate_b_anti_leakage.get("evaluator_only"),
        "evaluator-only fields must exactly match frozen Gate B",
    )
    for field in (
        "candidate_network_access",
        "candidate_filesystem_access",
        "candidate_git_metadata_access",
        "candidate_benchmark_repo_access",
    ):
        _expect(findings, execution.get(field) is False, f"{field} must remain false")
    _expect(
        findings,
        execution.get("candidate_calibration_freshness") == "not_yet_calibrated",
        "first headline observation must use the truthful cold-start calibration state",
    )

    cold_start = execution.get("cold_start_policy", {})
    _expect(
        findings,
        cold_start.get("headline_uses_uncalibrated_state") is True,
        "cold-start headline policy must be enabled",
    )
    _expect(
        findings,
        cold_start.get("same_corpus_post_calibration_rerun_headline_eligible") is False,
        "same-corpus post-calibration reruns must not be headline eligible",
    )
    _expect(
        findings,
        cold_start.get("future_independent_prospective_cases_required_for_steady_state_claim") is True,
        "steady-state claims must require future independent cases",
    )

    d1 = protocol.get("D1_input_materialization", {})
    _expect(findings, d1.get("state_at_protocol_creation") == "not_materialized", "D1 must start unmaterialized")
    _expect(findings, d1.get("candidate_execution_forbidden") is True, "candidate execution must be forbidden in D1")
    _expect(findings, d1.get("anti_leakage_assertion_required") is True, "D1 must require anti-leakage assertion")
    _expect(findings, d1.get("manifest_freeze_required_before_D2") is True, "D1 manifest must freeze before D2")

    d2 = protocol.get("D2_first_observation", {})
    for field in (
        "candidate_invocation_starts_observation_lock",
        "all_raw_candidate_outputs_preserved",
        "partial_attempts_preserved",
        "identical_replay_for_infrastructure_recovery_allowed",
        "replay_requires_identical_candidate_input_and_protocol_blobs",
        "result_replacement_forbidden",
        "result_append_only_history_required",
    ):
        _expect(findings, d2.get(field) is True, f"D2.{field} must remain true")
    _expect(
        findings,
        d2.get("candidate_or_protocol_tuning_after_first_invocation") == "invalid_experiment",
        "candidate/protocol tuning after first invocation must invalidate the experiment",
    )
    _expect(
        findings,
        d2.get("threshold_or_baseline_tuning_after_first_invocation") == "invalid_experiment",
        "threshold/baseline tuning after first invocation must invalidate the experiment",
    )

    scoring = protocol.get("scoring_policy")
    if not isinstance(scoring, dict):
        findings.append("scoring_policy must be an object")
        scoring = {}
    _expect(findings, scoring.get("source") == "frozen_inputs.gate_b", "scoring must source frozen Gate B")
    _expect(findings, scoring.get("overrides_forbidden") is True, "Gate D scoring overrides must be forbidden")
    _expect(
        findings,
        scoring.get("ground_truth_visibility") == "evaluator_only_after_candidate_output_is_fixed",
        "ground truth must remain evaluator-only until candidate output is fixed",
    )
    _expect(
        findings,
        scoring.get("static_comparator_candidates") == STATIC_METHODS,
        "static comparator candidates must be the three preregistered static baselines",
    )

    selector = scoring.get("strongest_safe_static_selection", {})
    eligibility = selector.get("eligibility", {})
    frozen_safety = gate_b.get("scoring", {}).get("safety", {})
    _expect(
        findings,
        eligibility.get("false_safe_critical_max") == frozen_safety.get("false_safe_critical_max"),
        "static comparator safety threshold must match frozen Gate B",
    )
    _expect(
        findings,
        eligibility.get("critical_recall_min") == frozen_safety.get("critical_recall_min"),
        "static comparator critical recall threshold must match frozen Gate B",
    )
    _expect(
        findings,
        selector.get("primary_order") == "lowest_family_balanced_excess_selection",
        "strongest-safe-static primary order must be fixed before observation",
    )
    _expect(findings, selector.get("tie_break_1") == "lowest_manual_interventions", "static tie-break 1 drifted")
    _expect(findings, selector.get("tie_break_2") == "lexicographic_method_id", "static tie-break 2 drifted")

    metrics = scoring.get("metric_definitions", {})
    required_metrics = {
        "case_excess_selection",
        "family_excess_selection",
        "family_balanced_excess_selection",
        "headline_excess_reduction",
        "zero_static_excess_policy",
        "repository_win",
        "family_win",
        "critical_recall",
        "false_safe_critical",
        "review_burden",
    }
    _expect(findings, required_metrics <= set(metrics), "Gate D metric definitions are incomplete")

    maintenance = scoring.get("maintenance_accounting", {})
    _expect(
        findings,
        maintenance.get("common_behavior_catalog_cost_excluded_from_all_methods") is True,
        "common behavior-catalog cost must be treated symmetrically",
    )
    _expect(
        findings,
        maintenance.get("method_specific_manual_mapping_entries_counted") is True,
        "method-specific mappings must be counted",
    )

    decision_rules = protocol.get("decision_rules", {})
    frozen_kill = gate_b.get("kill_rules", {})
    _expect(
        findings,
        decision_rules.get("critical_safety_failure") == "KILL_OR_NARROW_BIG",
        "critical safety failure must kill or narrow BIG",
    )
    _expect(
        findings,
        decision_rules.get("static_pareto_dominance") == "KILL_OR_NARROW_BIG",
        "static Pareto dominance must kill or narrow BIG",
    )
    _expect(
        findings,
        decision_rules.get("differentiation_threshold_failure") == "NO_DIFFERENTIATION_CLAIM",
        "differentiation failure must prohibit a differentiation claim",
    )
    _expect(
        findings,
        frozen_kill.get("post_observation_tuning") == "invalid_experiment",
        "frozen Gate B must still classify post-observation tuning as invalid",
    )

    required_record = protocol.get("required_first_observation_record")
    _expect(
        findings,
        isinstance(required_record, list) and set(required_record) == REQUIRED_FIRST_OBSERVATION_FIELDS,
        "first-observation record fields must match the preregistered closed set",
    )

    if require_freeze_ready:
        _expect(
            findings,
            protocol.get("protocol_base_commit") == candidate.get("main_merge_sha"),
            "freeze-ready protocol must be anchored to the mainline-verified Gate C merge",
        )
        _expect(
            findings,
            protocol.get("source_of_truth_issue") == "https://github.com/TensorScholar/proofdiff/issues/18",
            "freeze-ready protocol must point to Issue #18",
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-freeze-ready", action="store_true")
    args = parser.parse_args()

    protocol = _load(PROTOCOL_PATH)
    findings = validate_protocol(protocol, require_freeze_ready=args.require_freeze_ready)
    if findings:
        raise SystemExit("Gate D protocol validation failed:\n" + "\n".join(findings))
    print("Gate D protocol validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
