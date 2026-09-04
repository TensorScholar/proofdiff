from __future__ import annotations

import builtins

import pytest

from benchmarks.phase8b.big_candidate import select_with_big


def _behavior(
    behavior_id: str,
    description: str,
    *,
    risk: str = "medium",
    surface_tags: list[str] | None = None,
) -> dict[str, object]:
    return {
        "behavior_id": behavior_id,
        "description": description,
        "risk": risk,
        "surface_tags": surface_tags or [],
    }


def test_direct_semantic_impact_selects_behavior_with_provenance() -> None:
    result = select_with_big(
        sources={"pkg/core.py": "def validate_payment_tool():\n    return True\n"},
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("payment-validation", "validate payment tool")],
        calibration_freshness="fresh",
    )

    assert result.selected_ids == ("payment-validation",)
    proof = result.selected_proofs["payment-validation"]
    assert proof["impact_path"][0] == "source:pkg/core.py"
    assert proof["impact_path"][-1] == "behavior:payment-validation"
    assert proof["edge_classes"] == ["declared_semantic"]
    assert proof["triggering_change_nodes"] == ["source:pkg/core.py"]


def test_transitive_program_impact_reaches_behavior_beyond_changed_file() -> None:
    result = select_with_big(
        sources={
            "pkg/core.py": "def normalize_payload(value):\n    return value\n",
            "pkg/service.py": (
                "from pkg.core import normalize_payload\n\n"
                "def execute_approval_flow(value):\n"
                "    return normalize_payload(value)\n"
            ),
        },
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("approval-flow", "execute approval flow")],
        calibration_freshness="fresh",
    )

    assert result.selected_ids == ("approval-flow",)
    proof = result.selected_proofs["approval-flow"]
    assert proof["impact_path"] == [
        "source:pkg/core.py",
        "source:pkg/service.py",
        "behavior:approval-flow",
    ]
    assert proof["edge_classes"] == ["static_program", "declared_semantic"]


def test_unrelated_sibling_behavior_is_skipped_with_bounded_proof() -> None:
    result = select_with_big(
        sources={
            "pkg/core.py": "def validate_payment_tool():\n    return True\n",
            "pkg/report.py": "def render_summary():\n    return 'ok'\n",
        },
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("report-rendering", "render summary", risk="low")],
        calibration_freshness="fresh",
    )

    assert result.selected_ids == ()
    assert not result.review
    proof = result.skip_proofs["report-rendering"]
    assert proof["no_path_reason"] == "no_admissible_path_from_changed_source_to_behavior"
    assert proof["uncertainty_state"] == "bounded_static_analysis"
    assert proof["reachable_source_nodes"] == ["source:pkg/core.py"]
    assert proof["unresolved_local_imports"] == []
    assert proof["dynamic_import_uncertainty_sites"] == []
    assert proof["analysis_scope"] == {
        "python_files_total": 2,
        "python_files_parsed": 2,
        "python_files_parse_failed": 0,
    }


def test_import_cycle_terminates_and_preserves_shortest_impact_path() -> None:
    result = select_with_big(
        sources={
            "pkg/a.py": "from pkg.b import beta_route\n\ndef alpha_service():\n    return beta_route()\n",
            "pkg/b.py": "from pkg.a import alpha_service\n\ndef beta_route():\n    return alpha_service\n",
        },
        changed_paths=["pkg/a.py"],
        behaviors=[_behavior("beta-route", "beta route")],
        calibration_freshness="fresh",
    )

    assert result.selected_ids == ("beta-route",)
    assert result.selected_proofs["beta-route"]["impact_path"] == [
        "source:pkg/a.py",
        "source:pkg/b.py",
        "behavior:beta-route",
    ]


def test_unresolved_changed_path_forces_review_and_high_critical_widening() -> None:
    result = select_with_big(
        sources={"pkg/core.py": "def stable():\n    return True\n"},
        changed_paths=["pkg/missing.py"],
        behaviors=[
            _behavior("medium", "unrelated medium", risk="medium"),
            _behavior("high", "unrelated high", risk="high"),
            _behavior("critical", "unrelated critical", risk="critical"),
        ],
        calibration_freshness="fresh",
    )

    assert result.review
    assert result.selected_ids == ("critical", "high")
    assert "unresolved_changed_paths=1" in result.reasons
    assert "uncertainty:widen_high_critical" in result.reasons


def test_parse_failure_in_changed_source_forces_review_and_widening() -> None:
    result = select_with_big(
        sources={"pkg/core.py": "def broken(:\n    pass\n"},
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("high", "unrelated high", risk="high")],
        calibration_freshness="fresh",
    )

    assert result.review
    assert result.selected_ids == ("high",)
    assert "parse_failed_changed_paths=1" in result.reasons


def test_uncalibrated_candidate_cannot_issue_confident_skips() -> None:
    result = select_with_big(
        sources={
            "pkg/core.py": "def stable_core():\n    return True\n",
            "pkg/safety.py": "def high_risk_guard():\n    return True\n",
        },
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("high-risk-guard", "high risk guard", risk="high")],
    )

    assert result.review
    assert result.selected_ids == ("high-risk-guard",)
    assert "calibration:not_yet_calibrated" in result.reasons
    assert "uncertainty:widen_high_critical" in result.reasons


def test_literal_dynamic_import_is_resolved_as_static_program_evidence() -> None:
    result = select_with_big(
        sources={
            "pkg/provider.py": "def send_request():\n    return 'ok'\n",
            "pkg/consumer.py": (
                "import importlib\n\n"
                "provider = importlib.import_module('pkg.provider')\n\n"
                "def execute_remote_provider():\n"
                "    return provider.send_request()\n"
            ),
        },
        changed_paths=["pkg/provider.py"],
        behaviors=[_behavior("remote-provider", "execute remote provider", risk="high")],
        calibration_freshness="fresh",
    )

    assert not result.review
    assert result.selected_ids == ("remote-provider",)
    proof = result.selected_proofs["remote-provider"]
    assert proof["impact_path"] == [
        "source:pkg/provider.py",
        "source:pkg/consumer.py",
        "behavior:remote-provider",
    ]
    assert proof["edge_classes"] == ["static_program", "declared_semantic"]
    assert any(item.startswith("python_dynamic_import_literal:") for item in proof["edge_provenance"])


def test_nonliteral_dynamic_import_forces_review_instead_of_false_skip() -> None:
    result = select_with_big(
        sources={
            "pkg/provider.py": "def send_request():\n    return 'ok'\n",
            "pkg/consumer.py": (
                "import importlib\n\n"
                "provider_name = choose_provider()\n"
                "provider = importlib.import_module(provider_name)\n\n"
                "def execute_dynamic_provider():\n"
                "    return provider.send_request()\n"
            ),
        },
        changed_paths=["pkg/provider.py"],
        behaviors=[_behavior("dynamic-provider", "execute dynamic provider", risk="high")],
        calibration_freshness="fresh",
    )

    assert result.review
    assert result.selected_ids == ("dynamic-provider",)
    assert "dynamic_import_uncertainty=1" in result.reasons
    assert "uncertainty:widen_high_critical" in result.reasons


def test_critical_policy_selection_records_triggering_change_context() -> None:
    result = select_with_big(
        sources={"pkg/core.py": "def ordinary_change():\n    return True\n"},
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("critical-approval", "external approval", risk="critical")],
        calibration_freshness="fresh",
    )

    proof = result.selected_proofs["critical-approval"]
    assert proof["triggering_change_nodes"] == ["source:pkg/core.py"]
    assert proof["selection_mode"] == "critical_policy"
    assert proof["impact_path"] == ["policy:critical", "behavior:critical-approval"]


def test_duplicate_behavior_ids_are_rejected() -> None:
    behaviors = [
        _behavior("duplicate", "first behavior"),
        _behavior("duplicate", "second behavior"),
    ]
    with pytest.raises(ValueError, match="duplicate behavior_id"):
        select_with_big(
            sources={"pkg/core.py": "def stable():\n    return True\n"},
            changed_paths=["pkg/core.py"],
            behaviors=behaviors,
            calibration_freshness="fresh",
        )


def test_empty_change_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="changed_paths must not be empty"):
        select_with_big(
            sources={"pkg/core.py": "def stable():\n    return True\n"},
            changed_paths=[],
            behaviors=[_behavior("stable", "stable")],
            calibration_freshness="fresh",
        )


def test_graph_digest_and_output_are_deterministic_under_input_ordering() -> None:
    sources_a = {
        "pkg/core.py": "def normalize_payload(value):\n    return value\n",
        "pkg/service.py": "from pkg.core import normalize_payload\n\ndef execute_flow(value):\n    return normalize_payload(value)\n",
    }
    sources_b = dict(reversed(list(sources_a.items())))
    behaviors_a = [
        _behavior("flow", "execute flow"),
        _behavior("other", "render unrelated summary", risk="low"),
    ]
    behaviors_b = list(reversed(behaviors_a))

    first = select_with_big(
        sources=sources_a,
        changed_paths=["pkg/core.py"],
        behaviors=behaviors_a,
        calibration_freshness="fresh",
    )
    second = select_with_big(
        sources=sources_b,
        changed_paths=["./pkg/core.py"],
        behaviors=behaviors_b,
        calibration_freshness="fresh",
    )

    assert first.graph_digest == second.graph_digest
    assert first.to_dict() == second.to_dict()


def test_candidate_execution_does_not_read_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_open(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"candidate attempted filesystem access: {args!r} {kwargs!r}")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    result = select_with_big(
        sources={"pkg/core.py": "def stable():\n    return True\n"},
        changed_paths=["pkg/core.py"],
        behaviors=[_behavior("stable", "stable core")],
        calibration_freshness="fresh",
    )
    assert result.selected_ids == ("stable",)
