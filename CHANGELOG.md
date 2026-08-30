# Changelog

## 0.1.0rc2 — Unreleased

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

## 0.1.0rc1 — Unreleased

- Introduced deterministic agent-manifest diffing.
- Added impact-based behavioral-contract selection.
- Added fixture trace replay and trajectory invariant evaluation.
- Added PASS, REVIEW, and BLOCK release decisions.
- Produced scoped, checksum-verifiable evidence bundles.
- Added GitHub-native workflows and a reproducible synthetic benchmark.
