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

A successful prospective cross-repository pilot preregistered while
`crewAIInc/crewAI` pull request #7184 was still open and unmerged.

It demonstrates:

- preregistration before external resolution;
- exact frozen base and candidate revisions;
- a ProofDiff-owned deterministic five-run reproduction;
- an eight-contract control universe with 1/8 relevant selection;
- independent GitHub Actions capture and preserved raw observations;
- PASS for the frozen repair and REVIEW for the reverse regression.

The target PR remained open and unmerged when the measured result was finalized.
This pilot is external prospective evidence for the frozen behavior; it is not
customer validation, general production recall, or product-market-fit evidence.

## Running examples

From the repository root:

```bash
python examples/agentguard-mcp-exit-race/prepare.py \
  --output .proofdiff/pilots/agentguard-mcp-exit-race
```

See each example directory README for its evidence boundary and execution details.
