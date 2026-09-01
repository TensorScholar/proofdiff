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

## Compatibility contract for v0.1.x

This section records the compatibility decisions accepted for the stable `v0.1.0` line. Release
candidates remain pre-stable, but any deviation from these decisions before `v0.1.0` must be
intentional and documented.

### Runtime and platform

- Supported CPython versions are 3.11, 3.12, 3.13, and 3.14.
- The release-blocking public CI matrix is Linux. macOS and Windows may work, but they are not a
  compatibility guarantee until equivalent CI coverage exists.
- YAML input is an optional capability exposed through the `proofdiff[yaml]` extra; JSON-only use
  has no mandatory runtime dependency.
- The canonical distribution channel for the `0.1.x` line is GitHub Releases. PyPI is not part of
  the compatibility contract unless it is explicitly introduced in a later release decision.

### Stable public surfaces

The following surfaces are compatibility-controlled after stable `v0.1.0`:

1. The documented CLI commands and required flags for `init`, `snapshot`, `diff`, `select`, `check`,
   and `verify`, plus `proofdiff --version`.
2. CLI process status semantics: `0` for PASS/success, `1` for REVIEW, `2` for BLOCK, and `3` for
   input, integrity, or verification errors. Human-readable console wording is not a machine API.
3. The package-level Python interface exported by `proofdiff.__all__`: `CheckRequest`, `Decision`,
   `DecisionStatus`, `run_check`, and `__version__`. Imports from internal `proofdiff.engine`,
   `proofdiff.domain`, `proofdiff.cli`, or `proofdiff.reporting` modules are not compatibility
   promises unless separately documented.
4. The checked-in manifest, contract, trace, and policy JSON Schemas under `schemas/`.
5. The documented closed-set evidence-bundle file layout and the semantics required by
   `proofdiff verify`.

### Schema evolution

The current input schemas are versioned with the ProofDiff package rather than by a required
in-document schema-version field. Within `0.1.x`, additive optional fields are permitted when older
readers remain functional. Adding new required fields, removing accepted fields, changing an
existing field's meaning, or tightening validation in a way that rejects previously valid `0.1.x`
inputs is a breaking change and requires either a new explicitly versioned schema surface or the
`0.2.0` line.

The same rule applies to evidence semantics: additive metadata may be introduced only when the
closed-set verifier and supported `0.1.x` consumers remain compatible. Renaming/removing evidence
files or changing the meaning of decision/provenance fields is breaking.

### Versioning and deprecation

After stable `v0.1.0`, patch releases in the `0.1.x` line must not intentionally break the public
surfaces above. A breaking change requires `0.2.0` or a separately versioned opt-in surface. When a
surface can be retired without an urgent security requirement, deprecation should be documented
before removal. Security fixes may reject previously accepted unsafe input when preserving the old
behavior would violate an explicit security invariant; such changes must be called out in release
notes.

Benchmark values, report prose, internal module layout, implementation details, and ordering of
non-contractual diagnostic text are not compatibility guarantees.

## Extension policy

Adapters for OpenTelemetry, MCP inventory, or provider trace formats should normalize external
data into the existing manifest and trace contracts. They must remain outside the critical core and
must not silently weaken validation. A hosted service, dashboard, distributed scheduler, and LLM
judge are explicitly outside the release-candidate architecture.
