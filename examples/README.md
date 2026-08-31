# ProofDiff examples

This directory contains runnable ProofDiff examples.

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

## Running examples

From the repository root:

```bash
python examples/agentguard-mcp-exit-race/prepare.py \
  --output .proofdiff/pilots/agentguard-mcp-exit-race
```

See each example directory README for details.
