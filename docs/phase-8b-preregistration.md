# Phase 8B Preregistration: Behavior-Impact Differentiation Falsification

Status: **corpus preregistration; BIG implementation prohibited**

Source of truth: [Issue #18](https://github.com/TensorScholar/proofdiff/issues/18)

## 1. Purpose

Phase 8A established a useful but insufficient result: ProofDiff behaved conservatively on three frozen external changes, but its selected-evidence count tied a simple static mapping on all three cases. Phase 8B therefore does not assume that selective behavior impact is a product moat.

The experiment asks one falsifiable question:

> Can a conservative, provenance-backed Behavior Impact Graph (BIG) preserve independently labeled critical behavior while producing materially better evidence selection and maintenance economics than preregistered static alternatives?

If the answer is no, the impact-selection thesis is killed or narrowed. ProofDiff may then pivot toward evidence-governed AI release assurance rather than polishing a commodity selector.

## 2. Experimental separation

Phase 8B is deliberately split into gates that must occur in order.

### Gate A — corpus freeze

Freeze the external change corpus, protected invariants, independent oracles, family correlation labels, criticality, and confounding risk.

No BIG result fields are allowed in `benchmarks/phase8b/corpus.json`.

### Gate B — baseline and scoring freeze

Before any BIG implementation or tuning, commit:

1. full-suite baseline definition;
2. static component/tag mapping;
3. path/file-rule mapping;
4. current ProofDiff v0.1.0 selection behavior;
5. scoring formulas and minimum win thresholds;
6. maintenance-cost accounting rules.

Gate B is not satisfied by this corpus PR. `experiment_status=preregistering` therefore remains load-bearing even after the corpus itself is frozen.

### Gate C — candidate implementation

Only after A and B are immutable may the minimal BIG candidate be implemented.

### Gate D — execution and calibration

Run every preregistered method against the same frozen cases and independent oracles, then perform the preregistered broader/full-run calibration.

### Gate E — product decision

Apply the kill/pivot rules without retuning thresholds after observing results.

## 3. Corpus design

The primary historical arm contains at least **20 newly qualified external changes across at least five repositories**. The three Phase 8A cases are retained as controls and do not count toward the twenty-new-case target.

The corpus intentionally mixes:

- streaming and tool-lifecycle failures;
- HITL, resume, approval, and durable-state failures;
- async/parallel control-flow failures;
- workflow/A2A propagation failures;
- fail-open routing/policy failures;
- sensitive-data and credential-boundary failures;
- untrusted code-execution isolation failures;
- configuration aliasing/state-ownership failures;
- dispatch-cycle/depth integrity failures.

This heterogeneity is required. A selector that works only for one framework's directory layout or one class of agent runtime bug has not demonstrated a defensible product wedge.

## 4. Inclusion rules

A primary historical case must satisfy all of the following before freeze:

1. It is represented by an immutable 40-hex base SHA and head SHA.
2. The head is an accepted upstream commit or otherwise independently verified historical upstream state.
3. The behavior oracle exists independently in the upstream change or a frozen external probe.
4. The oracle describes behavior, not merely changed lines.
5. The change exposes a plausible distinction between semantic impact and coarse component/path membership.
6. The case has explicit criticality and confounding-risk labels.
7. Correlated cases carry a shared `family_id`.
8. No BIG selection, decision, or observed-result field is present.

A GitHub synthetic `merge_commit_sha` is not sufficient evidence that a PR merged. During qualification, PRs with `merged_at=null` were excluded from the historical arm even when a synthetic merge SHA was exposed.

For an accepted commit, the experimental base is the actual first parent of that commit, not a mutable or stale PR `base.sha` snapshot.

## 5. Non-primary arms

### Controls

The three Phase 8A frozen pairs remain controls. They detect regressions in methodology and preserve the prior null differentiation result. They never inflate the Phase 8B new-case count.

### Hold

A hold case may be technically strong but too confounded, multi-fix, noisy, or incompletely pinned for the primary arm. It is excluded from success thresholds unless re-qualified before experiment execution through an explicit preregistration amendment.

### Prospective

An unmerged or not-yet-historical change may remain as a separately labeled prospective case. It cannot be used to claim historical external validation.

### Rejected

Research corrections and rejected candidates are preserved in Issue #19 or future ledger entries when useful. Rejection is evidence hygiene, not a failed experiment.

## 6. Ground truth

Ground truth is the set of preregistered protected invariants and independent regression oracles for each case.

The experiment does **not** define ground truth as:

- every changed file;
- every existing upstream test;
- every contract in the same directory;
- the BIG's own predicted impact;
- a post-hoc reviewer judgment after seeing the candidate result.

An oracle may contain multiple regression tests for one invariant. Counts must therefore distinguish **oracle tests** from **protected behaviors**. Safety recall is behavior-weighted, not inflated by duplicate parametrizations.

## 7. Correlation and confounding

Raw case counts are not treated as independent Bernoulli trials.

Cases sharing a semantic failure family carry the same `family_id`. The final report must include both:

- per-case results; and
- family-stratified results where one family contributes at most one logical win/loss to the headline differentiation conclusion.

High-confounding cases remain valuable for conservative safety evaluation but may not be used as the sole evidence of selection-efficiency superiority.

The validator warns when more than two qualified historical cases share a family.

## 8. Preregistered methods

The methods must be defined before BIG implementation.

### 8.1 Full suite

Reference ceiling for recall and reference floor for selectivity. It is not assumed economical.

### 8.2 Static component/tag mapping

A manually declared mapping from change components/tags to protected behaviors. Mapping must be frozen before candidate execution.

### 8.3 Path/file rules

A deterministic mapping from changed paths/file classes to protected behaviors. Rules must not inspect the known oracle outcome for a case during execution.

### 8.4 ProofDiff v0.1.0

The current released/core selection behavior, frozen before BIG work.

### 8.5 Behavior Impact Graph candidate

The minimal candidate may use only preregistered edge classes:

- declared semantic edges;
- static program edges;
- dynamic/trace evidence edges;
- historical evidence edges;
- critical invariant edges.

Unknown or ambiguous reachability must widen selection or force `REVIEW`. It may never silently justify a skip.

## 9. Skip-proof contract

A central hypothesis is that organizational buyers need more than a list of selected evals. They need a defensible explanation for non-selection.

For every protected behavior not selected by BIG, the evidence bundle must contain a machine-readable skip proof with:

1. the changed source nodes;
2. the candidate behavior node;
3. the edge classes considered;
4. the reason no admissible impact path was established;
5. the uncertainty state;
6. the calibration freshness used to permit the skip;
7. any policy rule that widened or prohibited the skip.

A missing, stale, cyclic, contradictory, or unknown proof must widen selection or cause `REVIEW`.

The experiment must not reward a smaller selection set that cannot explain its skips.

## 10. Safety metrics

Let `B` be preregistered protected behaviors and `C` the subset labeled critical.

### Behavior recall

`behavior_recall = impacted_protected_behaviors_selected / impacted_protected_behaviors`

### Critical recall

`critical_recall = impacted_critical_behaviors_selected / impacted_critical_behaviors`

### Critical omission count

Number of independently labeled critical impacted behaviors for which the method neither selects the required evidence nor conservatively escalates according to preregistered policy.

### False-safe count

A case is false-safe when the method emits a release-safe outcome while a preregistered critical oracle demonstrates an unaddressed regression.

**Hard safety gate: false-safe count must be zero.**

### Conservative escalation rate

Fraction of cases where uncertainty causes `REVIEW`/widening. Lower is not automatically better; unsafe confidence is worse than explicit uncertainty.

### Calibration miss rate

During preregistered broader/full-run calibration, fraction of behaviors that broader execution shows should have been selected but were skipped by the candidate.

## 11. Selection economics

For each method and case record:

- protected behaviors selected;
- executable contracts/evals selected;
- wall-clock execution time where comparable;
- model/provider calls where applicable;
- estimated or measured external-eval cost;
- reviewer evidence surface area.

Primary selectivity statistics:

`selection_ratio = selected_evidence_units / full_evidence_units`

`selection_savings = 1 - selection_ratio`

Efficiency claims are invalid if achieved by violating the safety gate.

## 12. Mapping economics

Selection count alone is insufficient because a handcrafted static mapping can be cheap at runtime while expensive to maintain.

Before execution, every method must define a maintenance ledger. Record at least:

- initial mapping/rule entries;
- distinct source concepts manually mapped;
- protected behaviors manually mapped;
- updates required when a new case is introduced;
- stale mappings discovered by calibration;
- human review actions needed to approve mapping changes;
- graph/rule bytes or logical entries as a reproducible secondary proxy.

Do not fabricate engineering-hour precision from retrospective estimates. Prefer directly countable maintenance actions and report time only when actually measured.

## 13. Auditability metrics

For each non-selected protected behavior, score whether the method can produce:

- deterministic provenance;
- a bounded reason for skip;
- uncertainty state;
- calibration freshness;
- policy attribution;
- evidence-bundle verification.

Static baselines may score well here if their rules are explicit. BIG receives no credit merely for being graph-shaped.

## 14. Minimum differentiation bar

The candidate is not considered differentiated merely because it selects fewer items on average.

At minimum it must satisfy all of the following:

1. zero false-safe critical outcomes;
2. no lower critical recall than the strongest preregistered static baseline;
3. materially lower selection burden on a meaningful subset of discriminative cases, not only controls;
4. no worse total mapping-maintenance burden after calibration;
5. auditable skip proofs for every candidate skip;
6. benefits that survive family-stratified reporting rather than one overrepresented repository/failure family;
7. no result that depends on changing corpus labels, mappings, or thresholds after observing BIG output.

The exact numerical superiority threshold for item 3 must be frozen in Gate B before BIG implementation. This document intentionally does not invent it after the corpus is known but before the baseline distributions are measured; Gate B must commit the threshold before candidate execution.

## 15. Kill and pivot rules

### Kill/narrow impact-selection thesis

If static tags or path rules tie or beat BIG on safety and selection while requiring equal or lower mapping maintenance, the current impact-selection moat is rejected.

Do not respond by adding graph infrastructure, vector databases, LLM judges, or enterprise surface area to rescue the thesis.

### Pivot candidate

If selection differentiation fails but evidence history, release policy, approvals, waivers, calibration, and audit workflow show independent value, narrow ProofDiff toward:

> Evidence-Governed AI Release Assurance

The commercial hypothesis would then be an open deterministic engine plus a paid organizational assurance/control plane, not paid eval execution.

## 16. Post-observation amendments

After the first candidate or baseline result is observed, the frozen corpus may not be silently edited.

A legitimate amendment must:

1. increment the corpus/amendment state;
2. identify the exact affected case or harness rule;
3. state whether the defect is corpus, oracle, environment, harness, baseline, or candidate related;
4. preserve the original observation in Git history and issue/PR evidence;
5. explain why the amendment does not tune toward a preferred product conclusion;
6. rerun all methods affected by the amendment.

Harness defects may be repaired after observation, but the repaired run must be labeled separately, as Phase 8A demonstrated.

## 17. Anti-leakage discipline

The corpus schema has `additionalProperties=false`, and the validator rejects reserved result/prediction keys before execution.

Natural-language notes are also part of the preregistration and must not be edited to encode observed BIG outputs after freeze.

No candidate implementation may read hidden expected-selection labels because the corpus intentionally contains only behavior ground truth, not the answer to which contracts BIG should select.

## 18. Freeze procedure

1. Run `python benchmarks/phase8b/validate_corpus.py`.
2. Run `python benchmarks/phase8b/validate_corpus.py --require-freeze-ready`.
3. Verify CI, schema checks, Ruff, tests, security, and conformance on the preregistration branch.
4. Change `corpus_status` from `draft` to `frozen` and set an RFC 3339 `frozen_at` timestamp.
5. Rerun all checks.
6. Merge the preregistration PR.
7. Do not implement BIG yet. Freeze Gate B baselines and scoring next.

The merged Git commit is the immutable corpus snapshot used by later runs.

## 19. Current authorization state

At the time this document is introduced:

- corpus qualification: in final validation;
- corpus target: 20 new historical cases / 5 repositories / 3 Phase 8A controls;
- BIG implementation: **NOT AUTHORIZED**;
- pricing: **NOT DECIDED**;
- SaaS/control-plane implementation: **NOT AUTHORIZED**.

The next engineering work after corpus freeze is baseline/scoring preregistration, not product feature construction.
