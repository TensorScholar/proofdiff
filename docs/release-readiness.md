# Release readiness

## Current status

`0.1.0rc2` is an engineering release candidate, not a production-ready declaration.

## Proven by the packaged local validation

The handoff includes raw logs and checksums for the commands actually run. Current local gates cover:

- strict input and secret-persistence adversarial tests;
- conservative manifest and schema change analysis;
- impact selection, replay, comparison, and decision semantics;
- closed-set evidence generation and tamper detection;
- branch-aware coverage enforcement;
- JSON Schema validation for examples and policy;
- compilation, static source checks, deterministic benchmark execution;
- reproducible local wheel/sdist construction and isolated wheel smoke testing.

Exact counts and percentages belong in the generated validation report rather than this durable
document.

## Configured but requiring external execution

- Ruff formatting/lint and strict mypy;
- Python 3.11/3.12/3.13/3.14 Linux matrix;
- standard PEP 517 `python -m build` and `twine check`;
- `pip-audit`, CodeQL, and GitHub artifact attestation;
- migration behavior against the current public AXIOM repository;
- a real agent-release pilot.

## Merge gates

1. Migration branch is based on the recorded public `origin/main` commit, or a changed baseline is
   reviewed before work continues.
2. Existing history is preserved; no force-push or orphan replacement.
3. All external quality, packaging, security, and example workflows pass.
4. Full diff and public claims receive human review.
5. Nothing is tagged, published, or renamed during local validation.

## Stable-release gates

At least one real pilot, resolution of pilot findings, documented compatibility decisions, signed
or attested artifacts, and reviewed stable-release notes.
