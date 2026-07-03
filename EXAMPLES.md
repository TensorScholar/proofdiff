# AXIOM Examples

These examples run locally without provider secrets.

## Fake-Provider Evaluation

```bash
axiom eval \
  --dataset-file examples/fake_eval/dataset.json \
  --provider-file examples/fake_eval/provider.json \
  --output-file /tmp/axiom-example-eval-result.json
```

## Trace Import

```bash
axiom trace-import \
  --trace-file examples/trace_import/traces.json \
  --output-file /tmp/axiom-example-trace-cases.json \
  --dataset-id dataset-example
```

## Regression Promotion

```bash
axiom promote-regressions \
  --run-file examples/regression_promotion/run.json \
  --test-cases-file examples/regression_promotion/test_cases.json \
  --output-file /tmp/axiom-example-promotion.json \
  --suite-id suite-example \
  --suite-name "Example promoted failures"
```

## CI Gate Usage

Generate a gate result from a precomputed evaluation summary:

```bash
axiom summarize-gate \
  --summary-file examples/ci_gate/summary.json \
  --output-file /tmp/axiom-example-gate.json \
  --min-pass-rate 1.0 \
  --max-error-rate 0.0
```

Then check that gate result:

```bash
axiom gate --result-file /tmp/axiom-example-gate.json
```
