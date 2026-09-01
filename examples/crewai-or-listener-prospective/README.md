# CrewAI OR-listener prospective pilot

This directory contains a **prospective, cross-repository ProofDiff validation pilot** against an open CrewAI change.

Target:

- repository: `crewAIInc/crewAI`;
- issue: `#7183` — `or_()` join cancels parallel listener branches that should complete;
- pull request: `#7184` — `fix(flow): preserve parallel branches feeding OR listeners`;
- frozen base: `ec53d6f53448fcc7842f4d4d5f3272d2e7782557`;
- frozen candidate: `18a7a2d3a60c852733ab0fff2f1d94ef3f4808ed`.

At registration time, pull request #7184 was open and unmerged. The registration commit must land in ProofDiff before any live probe results are added to this directory. That commit establishes the hypotheses, contract universe, acceptance criteria, and frozen target revisions before external maintainer resolution.

## Registered behavior claim

A downstream `or_()` condition may decide when its listener fires, but it must not turn independently triggered producer listeners into a first-wins cancellation race.

The registered probe requires:

- both independently triggered producer branches to complete;
- the downstream OR join to fire exactly once;
- no probe runtime errors;
- five deterministic repetitions per frozen revision.

The frozen baseline must reproduce the reported incomplete-producer behavior in at least four of five runs. The frozen candidate must satisfy the registered behavior in all five runs.

## Why this target

This target is materially stronger validation than the historical AgentGuard retrospective:

- CrewAI is an external public repository with no ProofDiff-author affiliation recorded in this pilot;
- the target PR was still open when the hypothesis was registered;
- the behavior is deterministic and can be reproduced without an LLM, API key, external tool, or live model provider;
- the bug can skip branch state updates, tool calls, or other side effects, making it a meaningful release-assurance behavior rather than a cosmetic change.

Candidate-authored test claims and automated review summaries are context only. They are not counted as independent pilot outcome evidence.

## Pilot phases

1. **Registration** — freeze target SHAs, behavior claim, contract universe, expected selection, expected ProofDiff decisions, and failure criteria.
2. **Independent capture** — execute the same fixed reproduction against the frozen base and candidate revisions on an isolated runner.
3. **ProofDiff analysis** — translate captured observations deterministically into manifests/traces and run the registered contract set in both chronological and reverse directions.
4. **External resolution** — record the later maintainer disposition of CrewAI PR #7184 separately from the registered prediction.
5. **Finalization** — publish measured pilot results and explicit limitations without rewriting the preregistration.

## Registered contract universe

The pilot freezes eight contracts. Exactly one is expected to be relevant to the source-only change:

`flow.parallel_or_producers_complete`

The other seven contracts are deliberate unrelated controls. Registered expected selection is 1/8, or an 87.5% suite reduction, with no fallback.

## Non-claims

Even a successful pilot does not establish production recall, general semantic recall, customer validation, product-market fit, or safety of CrewAI. It validates only the frozen behavior and ProofDiff decision path defined in `registration.json`.

No result file belongs in this directory until the registration has been merged to ProofDiff `main`.
