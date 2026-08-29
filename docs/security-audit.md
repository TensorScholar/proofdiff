# Security hardening review — 0.1.0rc2

This review records the release-candidate security posture; it is not a third-party audit.

## Hardened in rc2

- duplicate-key and non-finite JSON/YAML rejection;
- bounded input size, nesting, records, events, output, and metrics;
- strict identifiers, booleans, unique IDs, unknown-field handling, and executable contracts;
- conservative tool-safety, policy-scope, schema, and unknown-change classification;
- one-way protection of raw secret-like configuration and credential schema literals;
- evidence input consistency and exact selected-contract/result/comparison linkage;
- atomic evidence writes and closed-set verification;
- local-source installation in the composite GitHub Action.

## Review priorities for the migration branch

- cross-platform path and symlink behavior on Windows/macOS/Linux;
- property tests for nested JSON Schema combinations;
- parser resource limits under hostile inputs;
- package dependency and workflow supply-chain review;
- external attestation of release artifacts;
- pilot validation with real tool and policy manifests.

## Non-goals

ProofDiff is not runtime enforcement. AgentGuard or equivalent controls must authorize live actions;
ProofDiff only contributes pre-deployment release evidence.
