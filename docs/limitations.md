# Limitations and non-claims

ProofDiff does not prove that an agent is safe, correct, compliant, or free from regressions. It
evaluates declared behavioral contracts against supplied normalized manifests and fixture traces.

- Contract selection is only as complete as declared coverage and recognized manifest surfaces.
- Conservative schema analysis may request review for changes that are behaviorally harmless.
- Fixture replay cannot predict stochastic providers, external tool state, latency, outages, or
  prompt-injection behavior not represented by fixtures.
- Critical decisions use deterministic assertions; semantic quality beyond those assertions is not
  automatically judged.
- Secret-like value protection is heuristic and one-way; production secrets should never enter
  fixtures or manifests.
- Evidence checksums provide integrity, not publisher authenticity.
- The benchmark is synthetic and maintained in this repository; it is not an external workload.
- The release candidate has no hosted UI, scheduler, trace collector, runtime gateway, or live MCP
  adapter.
- Public API and schema compatibility may change before stable `v0.1.0`.
