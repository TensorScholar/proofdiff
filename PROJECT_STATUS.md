# Project status

## Current release

`0.1.0rc2` — engineering release candidate for migration and independent review.

## Implemented

- strict manifest, contract, trace, policy, JSON, JSONL, and optional YAML ingestion;
- deterministic canonicalization and SHA-256 change identities;
- conservative semantic diff across agent, runtime, tool, schema, MCP, policy, retrieval,
  source, environment, and unknown surfaces;
- impact-based contract selection with mandatory critical contracts and fail-safe fallback;
- deterministic fixture replay and paired baseline/candidate classification;
- configurable PASS/REVIEW/BLOCK decision policy;
- closed-set evidence generation and verification;
- CLI, composite GitHub Action, examples, schemas, benchmark, packaging, and documentation.

## Locally verified for this candidate

The release handoff records exact commands, environment, test counts, branch-aware coverage,
benchmark results, package contents, and checksums. A claim is marked PASS only when its command
completed successfully in the build environment.

## Required before public merge

- apply candidate source to a branch rooted in the existing AXIOM repository history;
- run Ruff format/lint and strict mypy;
- run Python 3.11/3.12/3.13/3.14 Linux CI and CodeQL;
- run `pip-audit`, standard `python -m build`, and `twine check`;
- inspect the full migration diff and public README claims;
- do not tag, publish, or rename the repository until review approval.

## Required before stable v0.1.0

- at least one real agent-release pilot;
- resolution of pilot findings;
- reviewed public CI evidence;
- signed or attested release artifacts;
- explicit compatibility and migration notes.
