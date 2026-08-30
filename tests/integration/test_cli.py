from __future__ import annotations

from pathlib import Path

from proofdiff.cli.main import main

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "support-agent"


def test_blocked_candidate_end_to_end(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
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
            str(tmp_path / "evidence"),
            "--policy",
            str(EXAMPLE / "policy.json"),
        ]
    )
    assert code == 2
    assert "Decision: BLOCK" in capsys.readouterr().out
    assert (tmp_path / "evidence" / "checksums.txt").is_file()


def test_review_candidate_end_to_end(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    code = main(
        [
            "check",
            "--baseline",
            str(EXAMPLE / "baseline-manifest.json"),
            "--candidate",
            str(EXAMPLE / "candidate-review-manifest.json"),
            "--contracts",
            str(EXAMPLE / "contracts"),
            "--baseline-traces",
            str(EXAMPLE / "traces" / "baseline.jsonl"),
            "--candidate-traces",
            str(EXAMPLE / "traces" / "candidate-review.jsonl"),
            "--evidence",
            str(tmp_path / "evidence"),
        ]
    )
    assert code == 1
    assert "Decision: REVIEW" in capsys.readouterr().out


def test_init_creates_workspace(tmp_path: Path) -> None:
    assert main(["init", "--directory", str(tmp_path)]) == 0
    assert (tmp_path / ".proofdiff" / "policy.json").is_file()
    assert (tmp_path / "contracts" / "smoke" / "agent-responds.json").is_file()
