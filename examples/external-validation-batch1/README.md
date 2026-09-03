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
4. Refuse translation when probe execution errors, exits non-zero, or produces unstable observations.
5. Translate captured observations into ProofDiff manifests and fixture traces.
6. Run ProofDiff v0.1.0 unchanged in the repair direction.
7. Run the reverse direction as a counterfactual regression.
8. Run an all-contract full-suite baseline.
9. Verify every evidence bundle and write a machine-readable case result.
10. Upload raw captures, translated inputs, evidence bundles, and results as CI artifacts.

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

## Interpretation

A successful CI run means only that the frozen oracle was reproduced and the preregistered
ProofDiff assertions held for that case. Phase 8 still requires a larger external corpus, adoption
friction measurement, and real design-partner/commercial evidence before a v0.2 product thesis is
accepted.
