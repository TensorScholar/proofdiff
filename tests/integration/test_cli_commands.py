from __future__ import annotations

import json
from pathlib import Path

from proofdiff.cli.main import main

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "support-agent"


def test_snapshot_diff_select_and_verify_commands(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    snapshot = tmp_path / "snapshot.json"
    assert main(["snapshot", "--manifest", str(EXAMPLE / "baseline-manifest.json"), "--out", str(snapshot)]) == 0
    assert capsys.readouterr().out.startswith("sha256:")

    diff_out = tmp_path / "diff.json"
    assert main(
        [
            "diff",
            "--baseline",
            str(EXAMPLE / "baseline-manifest.json"),
            "--candidate",
            str(EXAMPLE / "candidate-review-manifest.json"),
            "--out",
            str(diff_out),
        ]
    ) == 0
    assert json.loads(diff_out.read_text(encoding="utf-8"))["changes"]

    select_out = tmp_path / "selection.json"
    assert main(
        [
            "select",
            "--baseline",
            str(EXAMPLE / "baseline-manifest.json"),
            "--candidate",
            str(EXAMPLE / "candidate-review-manifest.json"),
            "--contracts",
            str(EXAMPLE / "contracts"),
            "--out",
            str(select_out),
        ]
    ) == 0
    assert json.loads(select_out.read_text(encoding="utf-8"))["selected_ids"]

    evidence = tmp_path / "evidence"
    assert main(
        [
            "check",
            "--baseline",
            str(EXAMPLE / "baseline-manifest.json"),
            "--candidate",
            str(EXAMPLE / "candidate-block-manifest.json"),
            "--contracts",
            str(EXAMPLE / "contracts"),
            "--baseline-traces",
            str(EXAMPLE / "traces" / "baseline.jsonl"),
            "--candidate-traces",
            str(EXAMPLE / "traces" / "candidate-block.jsonl"),
            "--evidence",
            str(evidence),
        ]
    ) == 2
    capsys.readouterr()
    assert main(["verify", "--evidence", str(evidence)]) == 0
    assert "Verified" in capsys.readouterr().out


def test_cli_prints_json_when_no_output_file(capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(
        [
            "diff",
            "--baseline",
            str(EXAMPLE / "baseline-manifest.json"),
            "--candidate",
            str(EXAMPLE / "candidate-review-manifest.json"),
        ]
    ) == 0
    assert '"changes"' in capsys.readouterr().out
    assert main(
        [
            "select",
            "--baseline",
            str(EXAMPLE / "baseline-manifest.json"),
            "--candidate",
            str(EXAMPLE / "candidate-review-manifest.json"),
            "--contracts",
            str(EXAMPLE / "contracts"),
        ]
    ) == 0
    assert '"selected_ids"' in capsys.readouterr().out


def test_cli_errors_return_three(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert main(["verify", "--evidence", str(tmp_path)]) == 3
    assert "verification error" in capsys.readouterr().err
    assert main(["snapshot", "--manifest", str(tmp_path / "missing.json"), "--out", str(tmp_path / "x")]) == 3
    assert "ProofDiff error" in capsys.readouterr().err
