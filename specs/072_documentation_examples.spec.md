# Spec 072 — Documentation and Examples

## Objective

Add runnable local examples for the main AXIOM workflows and documentation that matches tested behavior.

This task must not add provider secrets, call external providers, add deployment behavior, or change CLI semantics.

## Required Behavior

Examples must cover:

- fake-provider evaluation,
- trace import,
- regression promotion,
- CI gate result generation and gate checking.

Documentation must:

- show local commands for each example,
- use repository-relative input fixture paths,
- write outputs to caller-selected paths,
- state that examples run without provider secrets.

## Verification

Run:

```bash
python3 -m pytest tests/examples
python3 -m compileall app
```

## Acceptance Criteria

- [ ] Fake-provider evaluation example is runnable.
- [ ] Trace import example is runnable.
- [ ] Regression promotion example is runnable.
- [ ] CI gate example is runnable.
- [ ] Documentation includes commands for each workflow.
- [ ] Examples require no provider secrets.
- [ ] Tests validate example behavior against the current CLI.
- [ ] Verification evidence exists in `.axiom/verification/task_072_verification.json`.
- [ ] Task report exists in `.axiom/reports/task_072_report.md`.
