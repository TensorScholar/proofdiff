# Changelog

## 0.1.0 — 2026-09-02

- Promotes the documented `0.1.x` CLI, exit-code, schema, evidence-bundle, and public Python compatibility contract to the first stable release line.
- Adds the preregistered external CrewAI OR-listener prospective pilot: the frozen base reproduced incomplete producer completion in 5/5 runs, the frozen candidate satisfied the registered behavior in 5/5 runs, and ProofDiff selected exactly 1/8 contracts with 87.5% suite reduction, classifying the repair as `PASS` / `fixed` and the reverse direction as `REVIEW` / `new_regression`.
- Hardens release origin and publication semantics so release tags must reference commits reachable from protected `main`, release jobs are serialized per ref, and existing release assets cannot be silently replaced with different bytes.
- Stabilizes Ruff and mypy suppression behavior across supported tool versions without changing ProofDiff runtime semantics.
- Retains explicit evidence boundaries: the prospective pilot validates one frozen deterministic external behavior and does not establish customer validation, general production recall, product-market fit, or overall target-system safety.

## 0.1.0rc3 — 2026-09-01

- Canonicalizes release artifacts on the PEP 517 backend as the sole wheel/sdist producer.
- Makes the release pipeline build, validate, and publish the same artifact set (wheel, sdist, SBOM, SHA256SUMS) with provenance attestation.
- Validates the `yaml` extra in wheel metadata and verifies both base and `proofdiff[yaml]` clean installs.
- Ensures the sdist includes runnable AgentGuard pilot helpers (`prepare.py`, `verify.py`) and tightens checksum coverage to wheel, sdist, and SBOM.
- Aligns CI/release workflows on `SOURCE_DATE_EPOCH` and removes duplicate build paths.

## 0.1.0rc2 — 2026-08-31

- Rejects duplicate JSON/YAML keys, non-finite values, malformed identifiers, ambiguous booleans,
  duplicate records, unsafe symlinks, and bounded-input violations.
- Adds conservative agent, tool-safety, opaque tool-configuration, policy-scope, and deeper JSON
  Schema change classification.
- Protects secret-like configuration values and credential defaults/examples with one-way digests
  before snapshots or evidence are persisted.
- Binds evidence to selected contract definitions, effective decision policy, and canonical trace
  digests.
- Makes evidence a verified closed set and rejects missing, unexpected, duplicate, unsafe, or
  modified entries.
- Recomputes changes, selection, replay results, comparisons, effective policy, and the final
  decision before evidence generation, rejecting forged or inconsistent derived values.
- Strengthens decision input validation and rejects symlinked path components.
- Makes the composite GitHub Action install the checked-out source rather than an unpublished PyPI
  package.
- Adds a policy schema, stricter public schemas, adversarial tests, and more explicit release gates.
- Adds the AgentGuard MCP exit-race retrospective validation pilot with pre-registered ground truth
  and deterministic conformance checks.

## 0.1.0rc1 — Unreleased

- Introduced deterministic agent-manifest diffing.
- Added impact-based behavioral-contract selection.
- Added fixture trace replay and trajectory invariant evaluation.
- Added PASS, REVIEW, and BLOCK release decisions.
- Produced scoped, checksum-verifiable evidence bundles.
- Added GitHub-native workflows and a reproducible synthetic benchmark.
