from __future__ import annotations

import copy
import json
from pathlib import Path

from benchmarks.phase8b.validate_gate_d import validate_protocol

ROOT = Path(__file__).parents[1]
PROTOCOL = json.loads((ROOT / "benchmarks" / "phase8b" / "gate_d.json").read_text(encoding="utf-8"))


def _messages(protocol: dict[str, object]) -> list[str]:
    return validate_protocol(protocol, require_freeze_ready=True)


def test_gate_d_protocol_is_freeze_ready_before_first_observation() -> None:
    assert _messages(PROTOCOL) == []


def test_gate_d_rejects_falsely_fresh_cold_start() -> None:
    mutated = copy.deepcopy(PROTOCOL)
    mutated["execution_design"]["candidate_calibration_freshness"] = "fresh"

    findings = _messages(mutated)
    assert any("truthful cold-start calibration state" in item for item in findings)


def test_gate_d_rejects_candidate_visibility_expansion() -> None:
    mutated = copy.deepcopy(PROTOCOL)
    mutated["execution_design"]["candidate_visible_fields"].append("case_id")

    findings = _messages(mutated)
    assert any("candidate-visible fields" in item for item in findings)


def test_gate_d_rejects_scoring_override() -> None:
    mutated = copy.deepcopy(PROTOCOL)
    mutated["scoring_policy"]["overrides_forbidden"] = False

    findings = _messages(mutated)
    assert any("scoring overrides" in item for item in findings)


def test_gate_d_rejects_post_observation_rescue_tuning() -> None:
    mutated = copy.deepcopy(PROTOCOL)
    mutated["D2_first_observation"]["candidate_or_protocol_tuning_after_first_invocation"] = "allowed"

    findings = _messages(mutated)
    assert any("invalidate the experiment" in item for item in findings)


def test_gate_d_rejects_nonfrozen_static_comparator() -> None:
    mutated = copy.deepcopy(PROTOCOL)
    mutated["scoring_policy"]["static_comparator_candidates"] = [
        "static_component_v1",
        "path_rules_v1",
        "new_static_after_observation",
    ]

    findings = _messages(mutated)
    assert any("three preregistered static baselines" in item for item in findings)
