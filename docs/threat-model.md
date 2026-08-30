# Threat model

## Protected assets

- integrity and scope of release decisions;
- behavioral contracts and fixture traces;
- manifest and policy identities;
- confidentiality of credentials accidentally embedded in configuration;
- evidence integrity and CI availability.

## Adversaries and failures considered

- malformed, oversized, deeply nested, duplicate-key, or non-finite input;
- schema changes that appear harmless but expand tool authority;
- weakened tool risk/destructive metadata;
- undeclared or unknown high-impact changes;
- missing critical traces or candidate regressions;
- inconsistent evidence inputs supplied through the Python API;
- checksum path traversal, duplicate entries, symlinks, missing files, and injected extra files;
- accidental persistence of raw secrets in runtime configuration or JSON Schema defaults/examples;
- network side effects or executable payloads during fixture replay;
- misleading release or benchmark claims.

## Mitigations

- strict bounded parsers and semantic validators;
- canonical JSON and deterministic SHA-256 identities;
- conservative schema-direction analysis with mixed/unknown changes routed to review;
- mandatory critical contracts and fail-safe selection for uncovered high-impact changes;
- explicit policy defaults and stable decision reason codes;
- exact evidence consistency checks and closed-set verification;
- one-way protection for secret-like values before persistence;
- no network calls, dynamic imports, subprocesses, `eval`, or `exec` in replay;
- scoped claims and documented benchmark limitations.

## Residual risks

- declared contract coverage can be incomplete or incorrect;
- JSON Schema semantic analysis is intentionally conservative, not a complete theorem prover;
- fixture traces cannot predict stochastic live-provider behavior;
- one-way secret protection is heuristic and not a substitute for secret scanning or a vault;
- a local attacker controlling the process can alter inputs before generation or replace the entire
  unsigned bundle afterward;
- checksum verification provides integrity only after a trusted copy of the checksum manifest is
  obtained;
- denial of service remains possible within configured limits on constrained machines.

## Out of scope

Runtime authorization, credential issuance, provider isolation, sandboxing, malicious installed
Python packages, distributed coordination, and authentication of unsigned local evidence bundles.
