from __future__ import annotations

from proofdiff.domain.models import ChangeSet, Comparison, ContractResult, Decision, Selection


def render_console(
    changeset: ChangeSet,
    selection: Selection,
    candidate_results: list[ContractResult],
    comparisons: list[Comparison],
    decision: Decision,
) -> str:
    lines = [
        "PROOFDIFF  RELEASE ASSURANCE",
        "",
        f"Baseline   {changeset.baseline_digest}",
        f"Candidate  {changeset.candidate_digest}",
        "",
        f"Changes    {len(changeset.changes)} ({changeset.highest_severity.value})",
        f"Contracts  {len(selection.selected_ids)} / {selection.total_contracts} selected",
        f"Reduction  {selection.reduction_ratio:.1%}",
        f"Fallback   {'yes' if selection.fallback_applied else 'no'}",
        "",
        "Results",
        f"  passed   {sum(item.passed for item in candidate_results)}",
        f"  failed   {sum(item.status.value == 'fail' for item in candidate_results)}",
        f"  missing  {sum(item.status.value == 'missing' for item in candidate_results)}",
        f"  regressions {sum(item.classification == 'new_regression' for item in comparisons)}",
        "",
        f"Decision: {decision.status.value}",
    ]
    for reason in decision.reasons:
        lines.append(f"  - {reason.code}: {reason.message}")
    return "\n".join(lines)


def render_markdown(
    changeset: ChangeSet,
    selection: Selection,
    candidate_results: list[ContractResult],
    comparisons: list[Comparison],
    decision: Decision,
) -> str:
    icon = {"PASS": "✅", "REVIEW": "⚠️", "BLOCK": "⛔"}[decision.status.value]
    rows = [
        "# ProofDiff release assurance",
        "",
        f"## {icon} Decision: `{decision.status.value}`",
        "",
        "| Signal | Value |",
        "|---|---:|",
        f"| Manifest changes | {len(changeset.changes)} |",
        f"| Highest change severity | `{changeset.highest_severity.value}` |",
        f"| Contracts selected | {len(selection.selected_ids)} / {selection.total_contracts} |",
        f"| Suite reduction | {selection.reduction_ratio:.1%} |",
        f"| Candidate passes | {sum(item.passed for item in candidate_results)} |",
        f"| Candidate failures | {sum(item.status.value == 'fail' for item in candidate_results)} |",
        f"| Missing traces | {sum(item.status.value == 'missing' for item in candidate_results)} |",
        f"| New regressions | {sum(item.classification == 'new_regression' for item in comparisons)} |",
        "",
        "## Reasons",
        "",
    ]
    rows.extend(f"- **{reason.code}** — {reason.message}" for reason in decision.reasons)
    rows.extend(["", "## Changed surfaces", ""])
    if changeset.changes:
        rows.extend(
            f"- `{change.type.value}` · `{change.path}` · **{change.severity.value}** — {change.summary}"
            for change in changeset.changes
        )
    else:
        rows.append("- No manifest changes detected.")
    rows.extend(["", "## Scope", ""])
    rows.append(
        "This decision is scoped to the supplied manifests, selected behavioral contracts, and fixture traces. "
        "It is not proof of future live-provider behavior."
    )
    return "\n".join(rows)
