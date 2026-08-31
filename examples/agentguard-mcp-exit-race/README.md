# AgentGuard MCP exit-race retrospective pilot

Pilot ID: `AG-MCP-EXIT-001`

This is ProofDiff's first cross-repository retrospective pilot against a real historical change. It uses the merged AgentGuard PR #8, which fixed an MCP stdio shutdown race where stdout could reach EOF before the child process exit status became visible. The buggy proxy treated that transient state as forced shutdown and returned exit code `1`; the fix waits for natural exit within the existing bounded shutdown timeout and returns the child's successful exit state.

## Frozen baseline

- ProofDiff repository: `TensorScholar/proofdiff`
- ProofDiff pilot baseline: `5e2e3f748da51b466dcdf611d30374ecd2f4b66b`
- Target repository: `TensorScholar/agentguard`
- Historical PR: `#8` — `fix: allow natural MCP server exit after output drain`
- Buggy target revision: `0b6e72995fc981e8760c3eefe057eef9dc8d7429`
- Fixed target revision: `abe3c6d320ac4351bcd8a133ea546aa8a052ecf8`
- Historical merge commit: `abcd464c93ec4b859a01ff06fba250ad9ea026d8`

## Ground truth established before ProofDiff execution

The merged AgentGuard PR and its deterministic regression test establish the expected behavior:

1. stdout reaches EOF / the output-drain state completes;
2. the proxy gives the child a bounded opportunity to exit naturally;
3. a naturally exiting child must not be classified as forced shutdown;
4. the successful path must return exit code `0`.

The pilot contract universe contains ten curated behavioral contracts. Exactly one is declared relevant to the changed `source` surface: `mcp.natural_exit_after_output_eof`.

Pre-registered acceptance criteria:

- relevant-contract recall: `100%`;
- relevant-contract precision: `100%` for this curated contract universe;
- fail-safe fallback: not applied;
- suite reduction: at least `80%`;
- chronological repair (`buggy -> fixed`): `PASS`;
- counterfactual regression gate (`fixed -> buggy`): `REVIEW`;
- false `BLOCK`: `0`.

## Phase mapping

- **Phase 0** — freeze the current ProofDiff RC and claims: this file and `source-evidence.json`.
- **Phase 1** — pre-register real historical ground truth and success/failure criteria: `ground-truth.json`.
- **Phase 2** — translate the frozen historical record into ProofDiff manifests and normalized traces: `prepare.py`.
- **Phase 3** — run both chronological repair and reverse regression analyses in GitHub CI and assert the pre-registered outcomes.

## Evidence strength and limitations

This is a **real historical code change** from another repository, but it is not an independent external customer pilot and it does not use live Windows runtime capture. The normalized traces are deterministic reconstructions from the merged PR's documented failure mode, source diff, and regression-test semantics. The ten-contract universe is pilot-curated rather than an imported production regression suite.

Therefore this pilot can test ProofDiff's change selection, paired comparison, decision semantics, and evidence generation on a real cross-repository change. It cannot establish production recall, onboarding cost, live-provider behavior, or external product-market validation.

Run the pilot from the repository root:

```bash
python examples/agentguard-mcp-exit-race/prepare.py --output .proofdiff/pilots/agentguard-mcp-exit-race
```

The GitHub conformance workflow runs and verifies both directions automatically.
