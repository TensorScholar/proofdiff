# Architecture

ProofDiff is a local-first modular monolith with a functional core and imperative shell. The
architecture is intentionally small: release assurance benefits more from transparent semantics
and reproducibility than from distributed infrastructure.

```text
Untrusted files / CLI
        │
        ▼
Input validation and canonicalization
        │
        ├── manifest snapshot and semantic diff
        ├── impact-based contract selection
        ├── deterministic fixture replay
        ├── baseline/candidate comparison
        ├── decision policy
        └── closed-set evidence generation
```

## Modules

- `domain/models.py`: immutable release-assurance data structures and enums.
- `engine/io.py`: bounded strict JSON/JSONL and optional safe YAML I/O; atomic writes.
- `engine/canonical.py`: finite JSON normalization, digests, and secret-key helpers.
- `engine/manifest.py`: manifest validation, snapshotting, and secret-value protection.
- `engine/diff.py`: conservative change classification and schema-direction analysis.
- `engine/contracts.py`: behavioral-contract parsing and semantic validation.
- `engine/selector.py`: declared-impact selection plus fail-safe fallback.
- `engine/traces.py`: normalized deterministic fixture traces.
- `engine/replay.py`: invariant evaluation with no network or code execution.
- `engine/comparison.py`: paired baseline/candidate classifications.
- `engine/decision.py`: explicit PASS/REVIEW/BLOCK policy.
- `engine/evidence.py`: scoped claims, provenance, closed-set checksums, and verification.
- `engine/pipeline.py`: application orchestration.
- `cli/main.py`: exit-code-stable command-line shell.

## Dependency rules

1. Domain models import no engine, CLI, or reporting modules.
2. Deterministic engines do not perform network access.
3. Filesystem effects are limited to I/O, pipeline, evidence, snapshot, and CLI boundaries.
4. Decision logic consumes normalized domain values; it does not read files or invoke models.
5. Reporting renders existing decisions; it cannot change decision status.
6. Critical release decisions do not depend on an LLM judge.

## Trust boundaries

Manifests, contracts, traces, and policies are untrusted. Input parsers reject duplicate keys,
non-finite values, malformed identifiers, unsafe symlinks, ambiguous types, and configured size
limits. Tool-schema property names remain visible for compatibility analysis, while credential
literals in secret-like configuration fields and schema defaults/examples are replaced with
one-way digests before persistence.

The evidence verifier treats a bundle as a closed set. It rejects path traversal, duplicate
checksum entries, symlinks, directories, missing files, extra files, and content mismatches.
Checksums do not authenticate the producer; use an external signature or build attestation.

## Determinism

Identical normalized inputs produce identical semantic digests, selections, replay results, and
decisions. Evidence provenance contains generation time and platform metadata, so the entire bundle
is not byte-identical across runs; the decision inputs and content digests remain inspectable.

## Extension policy

Adapters for OpenTelemetry, MCP inventory, or provider trace formats should normalize external
data into the existing manifest and trace contracts. They must remain outside the critical core and
must not silently weaken validation. A hosted service, dashboard, distributed scheduler, and LLM
judge are explicitly outside the release-candidate architecture.
