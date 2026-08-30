# Benchmark card

## Name

`proofdiff-maintained-synthetic-change-selection-v1`

## Purpose

Exercise impact-based selection, deterministic behavior, and decision semantics on generated
manifests and contracts. It is a regression benchmark for this repository, not a claim about
production agent workloads.

## Configuration

- 300 deterministic scenarios
- 2,000 contracts
- 200 tools
- fixed seed: 20260728

## Recorded local result

See `benchmarks/results.json`. On the recorded Linux / Python 3.13.5 run, direct coverage recall
was 1.0 by construction, mean suite reduction was 96.52%, median selection latency was about
approximately 1 ms, identical manifests produced PASS, and an injected critical failure produced BLOCK.

## Interpretation

The recall result only demonstrates consistency with the benchmark's declared tool-to-contract
oracle. It does not establish completeness for undeclared relationships or external systems.
