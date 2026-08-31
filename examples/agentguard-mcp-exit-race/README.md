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

## Observed Phase 3 result

The registered experiment ran on branch head `d1e3035a307bb0ce1926b68d9f4a687628a77c05` and passed every pre-registered gate:

- one relevant contract selected from ten contracts;
- relevant-contract recall: `100%`;
- relevant-contract precision: `100%` within the curated pilot universe;
- selection reduction: `90%`;
- fail-safe fallback: not applied;
- chronological repair (`buggy -> fixed`): candidate contract passed, comparison classified `fixed`, decision `PASS`;
- reverse regression (`fixed -> buggy`): candidate contract failed, comparison classified `new_regression`, decision `REVIEW`;
- both closed evidence bundles passed `proofdiff verify`;
- false `BLOCK`: `0`.

GitHub Actions run `33410266525` validated the conformance pilot; CI run `33410266462` and CodeQL run `33410266580` also completed successfully. The machine-readable observation is recorded in `results.json`.

## Evidence strength and limitations

This is a **real historical code change** from another repository, but it is not an independent external customer pilot and it does not use live Windows runtime capture. The normalized traces are deterministic reconstructions from the merged PR's documented failure mode, source diff, and regression-test semantics. The ten-contract universe is pilot-curated rather than an imported production regression suite.

Therefore this pilot supports a narrower claim: the current ProofDiff deterministic core selected and classified the pre-registered behavior correctly for this real historical cross-repository change under the curated pilot model. It does **not** establish production recall, onboarding cost, live-provider behavior, independent customer validation, or product-market fit.

Run the pilot from the repository root:

```bash
python examples/agentguard-mcp-exit-race/prepare.py --output .proofdiff/pilots/agentguard-mcp-exit-race
```

The GitHub conformance workflow runs and verifies both directions automatically.
