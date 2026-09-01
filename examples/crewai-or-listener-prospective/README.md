# CrewAI OR-listener prospective pilot

This directory contains a **prospective, cross-repository ProofDiff validation pilot** against an open CrewAI change.

Target:

- repository: `crewAIInc/crewAI`;
- issue: `#7183` — `or_()` join cancels parallel listener branches that should complete;
- pull request: `#7184` — `fix(flow): preserve parallel branches feeding OR listeners`;
- frozen base: `ec53d6f53448fcc7842f4d4d5f3272d2e7782557`;
- frozen candidate: `18a7a2d3a60c852733ab0fff2f1d94ef3f4808ed`.

The preregistration was merged to protected ProofDiff `main` at
`e8d29240566e5740b562a7f059a03fc891c23c2c`. CrewAI pull request #7184 was rechecked immediately after that merge and was still open and unmerged. The frozen registration therefore precedes the external maintainer resolution.

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
- the target PR was still open when the hypothesis was registered and when the registration reached ProofDiff `main`;
- the behavior is deterministic and can be reproduced without an LLM, API key, external tool, or live model provider;
- the bug can skip branch state updates, tool calls, or other side effects, making it a meaningful release-assurance behavior rather than a cosmetic change.

Candidate-authored test claims and automated review summaries are context only. They are not counted as independent pilot outcome evidence.

## Independent execution harness

The live-capture phase uses only ProofDiff-owned probe/translation code:

- `probe.py` implements the fixed public reproduction;
- `capture.py` executes it five times in a fresh process against each frozen CrewAI revision;
- `prepare.py` translates the raw captures into source-only ProofDiff manifests and deterministic traces;
- `verify.py` enforces the preregistered capture, selection, comparison, and decision criteria.

`.github/workflows/crewai-prospective-pilot.yml` checks out the exact external SHAs with read-only credentials, installs each revision into an isolated Python 3.12 environment, disables telemetry for the probe, and uploads the raw captures and ProofDiff evidence as a GitHub Actions artifact. It does not run target-provided tests as pilot outcome evidence.

Dependency installation uses network access. The registered probe behavior itself requires no network, model call, API key, or external tool call.

## Measured result

The authoritative capture run completed successfully against the exact preregistered revisions.

Observed frozen baseline:

- 5/5 runs reproduced incomplete producer completion;
- the OR join fired exactly once in every run;
- no runtime errors occurred.

Observed frozen candidate:

- 5/5 runs completed both `fast` and `slow` producer branches;
- the OR join fired exactly once in every run;
- no runtime errors occurred.

ProofDiff selected exactly `flow.parallel_or_producers_complete` from the eight-contract universe, for an 87.5% selection reduction with no fallback. The prospective repair produced `PASS` with comparison `fixed`; the reverse direction produced `REVIEW` with comparison `new_regression`.

`results.json` records the compact measured outcome. `captures/` preserves the raw five-run observations, and `execution-evidence.json` records the authoritative GitHub Actions run and artifact lineage.

## Pilot phases

1. **Registration — complete**: target SHAs, behavior claim, contract universe, expected selection, expected ProofDiff decisions, and failure criteria are frozen on ProofDiff `main`.
2. **Independent capture — complete**: the fixed reproduction ran against the exact frozen base and candidate revisions in isolated environments.
3. **ProofDiff analysis — complete**: captured observations were translated deterministically and evaluated in both chronological and reverse directions.
4. **External resolution — pending**: CrewAI PR #7184 remained open and unmerged when the successful capture was finalized; its later maintainer disposition is recorded separately and cannot alter the preregistered result.
5. **Finalization — complete**: measured captures, compact results, and execution lineage are preserved without rewriting the preregistration.

## Registered contract universe

The pilot freezes eight contracts. Exactly one is expected to be relevant to the source-only change:

`flow.parallel_or_producers_complete`

The other seven contracts are deliberate unrelated controls. Registered expected selection is 1/8, or an 87.5% suite reduction, with no fallback.

## Non-claims

This successful pilot does not establish production recall, general semantic recall, customer validation, product-market fit, or safety of CrewAI. It validates only the frozen behavior and ProofDiff decision path defined in `registration.json`.

Measured results come from the independent live-capture artifact; the preregistration files were not rewritten after observation.
