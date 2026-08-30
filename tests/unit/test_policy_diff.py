from __future__ import annotations

from proofdiff.domain.models import ChangeType, Severity
from proofdiff.engine.diff import compare_manifests


def test_policy_allowed_tool_expansion_is_critical() -> None:
    baseline = {
        "agent": {"name": "a"},
        "runtime": {},
        "tools": [],
        "policy": {"allowed_tools": ["read"]},
    }
    candidate = {
        "agent": {"name": "a"},
        "runtime": {},
        "tools": [],
        "policy": {"allowed_tools": ["read", "delete"]},
    }
    change = compare_manifests(baseline, candidate).changes[0]
    assert change.type is ChangeType.POLICY_SCOPE_EXPANDED
    assert change.severity is Severity.CRITICAL
    assert change.metadata["added_allowed_tools"] == ["delete"]
