# ProofDiff examples

This directory contains runnable ProofDiff examples and registered validation pilots.

## support-agent

A minimal behavioral regression example.

It demonstrates:

- manifest change analysis;
- contract selection;
- deterministic trace replay;
- PASS / REVIEW / BLOCK behavior.

This example is intended for understanding the ProofDiff workflow.

## agentguard-mcp-exit-race

A real historical cross-repository retrospective pilot against a change
in the `TensorScholar/agentguard` repository.

It demonstrates:

- frozen historical input;
- pre-registered ground truth;
- deterministic adapter translation;
- evidence-backed retrospective analysis.

This pilot validates a narrow deterministic behavior claim.
It does not establish production recall, customer validation, or
product-market fit.

## crewai-or-listener-prospective

A prospective cross-repository pilot preregistered while `crewAIInc/crewAI`
pull request #7184 was still open and unmerged.

It freezes:

- target base and candidate revisions;
- an external public issue reproduction;
- the behavioral claim and five-run probe protocol;
- an eight-contract control universe;
- expected selection and decision outcomes;
- failure criteria before live capture and external maintainer resolution.

The preregistration is now on protected ProofDiff `main`. A dedicated read-only
GitHub Actions workflow performs independent capture against the exact frozen
CrewAI revisions and preserves the resulting ProofDiff evidence as a workflow
artifact.

## Running examples

From the repository root:

```bash
python examples/agentguard-mcp-exit-race/prepare.py \
  --output .proofdiff/pilots/agentguard-mcp-exit-race
```

See each example directory README for its evidence boundary and execution details.
