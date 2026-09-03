# ProofDiff External Validation — Batch 1

Batch 1 is the first post-v0.1.0 falsification exercise for ProofDiff's proposed
**change-conditioned assurance** wedge.

It is deliberately not a product demo and not a benchmark designed to maximize suite reduction.
The batch asks whether ProofDiff v0.1.0, unchanged, can connect independently observed behavior
changes to the protected evidence surface without silently omitting relevant behavior.

## Frozen cases

| Case | External project | Change | Status | Risk |
|---|---|---|---|---|
| B1-01 | `openai/openai-agents-python` | chained `$ref` strict-schema semantic preservation | merged historical fix | high |
| B1-02 | `CopilotKit/CopilotKit` | frontend tool + app-context propagation into LangGraph subgraphs | merged historical fix | high |
| B1-03 | `langchain-ai/langgraph` | HITL interrupt propagation through tool-call middleware | unmerged patch candidate | critical |

The immutable revisions and upstream references are recorded in `registration.json` and in the
preregistration comment on ProofDiff issue #15. The LangGraph candidate is intentionally and
permanently labeled **unmerged** unless upstream history later proves otherwise; this batch does not
convert a closed patch into an upstream acceptance claim.

## Experimental protocol

Each CI case follows the same evidence pipeline:

1. Check out the frozen baseline and candidate revisions.
2. Install each revision in an isolated environment using the target project's committed lockfile
   when available.
3. Run an independent deterministic probe three times against each revision.
4. Persist raw evidence and fail closed if a probe errors, exits non-zero, or produces unstable
   observations.
5. Translate successful captures into ProofDiff manifests and fixture traces.
6. Run ProofDiff v0.1.0 unchanged in the repair direction.
7. Run the reverse direction as a counterfactual regression.
8. Run an all-contract full-suite baseline.
9. Verify every evidence bundle and write a machine-readable case result.
10. Upload raw captures, translated inputs, evidence bundles, and results as CI artifacts.

The LangGraph environment resolves the frozen main `langgraph` runtime from the revision lockfile and
supplies the exact same-revision `libs/prebuilt` source through `PYTHONPATH`. This avoids dependency
re-resolution while executing the frozen ToolNode implementation under test.

The probes execute target behavior; they do not write the expected outcome directly into ProofDiff
traces. `prepare.py` only translates observed booleans/data into fixture records after capture.

## Baselines

For every case we compare:

- **Full suite:** every declared contract is forced to run by generated `always_run` copies.
- **Static tag/split baseline:** the preregistered protected contract IDs selected manually by
  component/category knowledge.
- **ProofDiff targeted selection:** the untouched v0.1.0 selector.

Batch 1 is a micro-suite. Contract-count reduction here is validation evidence only; it is not a
claim about customer ROI, production recall, safety, or dollars saved. A tie with the static baseline
is a valid null result and must be reported as such.

## First execution and post-observation repair

The first CI execution exposed two validation-harness defects, both preserved on issue #15 before
repair:

- the OpenAI case expected `PASS`, although the released v0.1.0 policy correctly returns `REVIEW`
  for a high-risk capability/tool-schema change even when the protected behavior is fixed;
- the initial LangGraph environment omitted the main `langgraph` package, and the capture wrapper did
  not immediately fail when all probe runs reported import errors.

Post-observation changes were restricted to validation infrastructure: fail-closed capture, the
correct frozen LangGraph runtime/source overlay, and expected exit codes matching the already
released policy. ProofDiff selector/evaluator/decision core, registered external revisions, and
protected contracts were not tuned to make the batch pass.

## Corrected Batch 1 result

| Case | Oracle | Targeted | Full | Static | Forward | Reverse | Protected omissions | False-safe |
|---|---:|---:|---:|---:|---|---|---:|---:|
| OpenAI Agents | 3/3 per revision | 1/3 | 3/3 | 1 | `REVIEW / fixed` | `REVIEW / new_regression` | 0 | 0 |
| CopilotKit | 3/3 per revision | 2/4 | 4/4 | 2 | `PASS / fixed` | `REVIEW / new_regression` | 0 | 0 |
| LangGraph | 3/3 per revision | 2/4 | 4/4 | 2 | `PASS / fixed` | `BLOCK / new_regression` | 0 | 0 |

### Supported by Batch 1

- all three frozen external behavioral oracles reproduced deterministically;
- no registered protected behavior was omitted;
- no registered false-safe decision was observed;
- the critical LangGraph reverse regression was blocked;
- evidence bundles verify and preserve deterministic forward/reverse classification;
- targeted execution avoids micro-suite work relative to the full declared suites.

### Not supported by Batch 1

ProofDiff did **not** beat the preregistered static tag/component baseline on selected-contract count
in any case:

- OpenAI: `1 = 1`;
- CopilotKit: `2 = 2`;
- LangGraph: `2 = 2`.

Therefore Batch 1 does not support claims that current v0.1.0 selection is superior to static
mapping, reduces mapping maintenance, reduces reviewer effort, provides production-scale recall,
creates customer ROI, or demonstrates willingness to pay.

The full-suite reductions are validation-only micro-suite measurements and must not be presented as
economic savings.

## Anti-gaming rules

- No core selector/diff/policy modification is allowed before the first result.
- A failing case stays in the corpus.
- If a case later motivates a product fix, preserve the original run and report the repaired run
  separately as post-observation evidence.
- Never relabel an ambiguous or unmerged upstream change to improve ProofDiff's apparent accuracy.
- Any false-safe omission of the registered critical LangGraph HITL behavior blocks a positive Phase
  8 conclusion until the failure is understood.

## Files

- `registration.json` — immutable Batch 1 case registry and experimental rules.
- `capture.py` — generic repeated subprocess capture protocol.
- `*_probe.py` — target-specific, network-free behavior probes.
- `contracts/<case>/` — protected contracts plus negative-control contracts.
- `prepare.py` — capture-to-ProofDiff translation.
- `make_full_contracts.py` — full-suite baseline generator.
- `policy.json` — conservative release policy.
- `verify.py` — preregistered oracle, selection, decision, and baseline assertions.

## Product decision

Batch 1 is a positive narrow conservative-assurance result and a **null differentiation result**.

The next falsification phase is issue #18: determine whether a calibrated, provenance-backed
Behavior Impact Graph can reduce mapping/evaluation burden versus static mappings while preserving
conservative behavior and producing explicit justification for both selected and skipped contracts.

If that experiment cannot beat static mapping on meaningful operational economics without
sacrificing assurance, ProofDiff should stop treating impact selection as the primary moat and
evaluate evidence-governed AI release assurance as the narrower product wedge.
