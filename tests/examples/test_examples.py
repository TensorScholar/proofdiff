from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from app.cli import main


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"


def test_fake_provider_evaluation_example_runs(tmp_path) -> None:
    output_file = tmp_path / "eval-result.json"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "eval",
            "--dataset-file",
            str(EXAMPLES / "fake_eval" / "dataset.json"),
            "--provider-file",
            str(EXAMPLES / "fake_eval" / "provider.json"),
            "--output-file",
            str(output_file),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert stdout.getvalue() == "AXIOM eval completed: run-example-eval\n"
    assert stderr.getvalue() == ""
    assert payload["status"] == "completed"
    assert payload["sample_results"][0]["metadata"]["metrics"][0]["passed"] is True


def test_trace_import_example_runs(tmp_path) -> None:
    output_file = tmp_path / "trace-cases.json"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "trace-import",
            "--trace-file",
            str(EXAMPLES / "trace_import" / "traces.json"),
            "--output-file",
            str(output_file),
            "--dataset-id",
            "dataset-example",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert stdout.getvalue() == "AXIOM trace import completed: 1 failed of 2 records\n"
    assert stderr.getvalue() == ""
    assert payload["output_kind"] == "test-cases"
    assert payload["items"][0]["id"] == "trace-case-trace-failed"


def test_regression_promotion_example_runs(tmp_path) -> None:
    output_file = tmp_path / "promotion.json"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "promote-regressions",
            "--run-file",
            str(EXAMPLES / "regression_promotion" / "run.json"),
            "--test-cases-file",
            str(EXAMPLES / "regression_promotion" / "test_cases.json"),
            "--output-file",
            str(output_file),
            "--suite-id",
            "suite-example",
            "--suite-name",
            "Example promoted failures",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert stdout.getvalue() == "AXIOM regression promotion completed: 2 cases promoted to suite-example\n"
    assert stderr.getvalue() == ""
    assert payload["promoted_count"] == 2
    assert payload["suite"]["cases"][0]["id"] == "regression-run-example-promotion-case-metric"


def test_ci_gate_example_runs(tmp_path) -> None:
    output_file = tmp_path / "gate.json"
    stdout = StringIO()
    stderr = StringIO()

    summarize_exit_code = main(
        [
            "summarize-gate",
            "--summary-file",
            str(EXAMPLES / "ci_gate" / "summary.json"),
            "--output-file",
            str(output_file),
            "--min-pass-rate",
            "1.0",
            "--max-error-rate",
            "0.0",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert summarize_exit_code == 0
    assert stdout.getvalue() == "AXIOM gate result written: run-example-gate\n"
    assert stderr.getvalue() == ""
    assert payload["passed"] is True

    gate_stdout = StringIO()
    gate_stderr = StringIO()
    gate_exit_code = main(
        ["gate", "--result-file", str(output_file)],
        stdout=gate_stdout,
        stderr=gate_stderr,
    )

    assert gate_exit_code == 0
    assert gate_stdout.getvalue() == "AXIOM gate passed: run-example-gate\n"
    assert gate_stderr.getvalue() == ""


def test_examples_documentation_mentions_runnable_commands() -> None:
    examples_doc = (ROOT / "EXAMPLES.md").read_text(encoding="utf-8")

    for command in [
        "axiom eval",
        "axiom trace-import",
        "axiom promote-regressions",
        "axiom summarize-gate",
        "axiom gate",
    ]:
        assert command in examples_doc
