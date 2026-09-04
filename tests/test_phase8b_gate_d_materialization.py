from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
from benchmarks.phase8b import materialize_gate_d_inputs as materializer
from benchmarks.phase8b.validate_gate_d_materialization import _artifact_path


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "ProofDiff Gate D1")
    _git(repo, "config", "user.email", "gate-d1@example.invalid")
    return repo


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_materializer_never_imports_or_invokes_big_candidate() -> None:
    path = Path(materializer.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_modules: set[str] = set()
    referenced_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced_names.add(node.attr)

    assert not any(module.endswith("big_candidate") for module in imported_modules)
    assert "select_with_big" not in referenced_names


def test_candidate_payload_has_exact_frozen_visible_keys_and_no_case_identity() -> None:
    payload = materializer._candidate_payload(
        repo="example/project",
        base_sha="a" * 40,
        head_sha="b" * 40,
        baseline_sources={"src/core.py": "def stable():\n    return True\n"},
        candidate_sources={"src/core.py": "def stable():\n    return False\n"},
        production_diff={
            "changed_paths": ["src/core.py"],
            "rename_policy": "disabled_decompose_to_delete_add",
            "unified_diff": "diff --git a/src/core.py b/src/core.py\n",
            "unified_diff_sha256": "0" * 64,
        },
        behavior_catalog=[
            {
                "behavior_id": "b_1",
                "repo": "example/project",
                "description": "stable behavior",
                "surface_tags": ["stable"],
                "risk": "medium",
            }
        ],
        method_config={"schema_version": "1.0"},
    )

    assert set(payload) == materializer.CANDIDATE_VISIBLE_FIELDS
    assert "case_id" not in payload
    assert "oracle" not in payload
    assert "ground_truth_behavior_ids" not in payload


def test_candidate_payload_rejects_evaluator_only_key_recursively() -> None:
    with pytest.raises(ValueError, match="evaluator-only keys"):
        materializer._candidate_payload(
            repo="example/project",
            base_sha="a" * 40,
            head_sha="b" * 40,
            baseline_sources={"src/core.py": "pass\n"},
            candidate_sources={"src/core.py": "pass\n"},
            production_diff={"changed_paths": ["src/core.py"]},
            behavior_catalog=[{"behavior_id": "b_1", "case_id": "forbidden"}],
            method_config={},
        )


def test_canonical_payload_digest_is_order_independent() -> None:
    first = {
        "repo": "example/project",
        "production_diff": {"changed_paths": ["b.py", "a.py"]},
        "sources": {"b.py": "b", "a.py": "a"},
    }
    second = {
        "sources": {"a.py": "a", "b.py": "b"},
        "production_diff": {"changed_paths": ["b.py", "a.py"]},
        "repo": "example/project",
    }
    assert materializer.canonical_sha256(first) == materializer.canonical_sha256(second)


def test_source_snapshot_uses_frozen_path_filter_and_locked_python_projection(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()
    (repo / "src" / "core.py").write_text("def core():\n    return 1\n", encoding="utf-8")
    (repo / "src" / "config.json").write_text('{"enabled": true}\n', encoding="utf-8")
    (repo / "tests" / "test_core.py").write_text("def test_core():\n    assert True\n", encoding="utf-8")
    (repo / "docs" / "guide.py").write_text("SHOULD_NOT_LEAK = True\n", encoding="utf-8")
    sha = _commit(repo, "baseline")

    snapshot = materializer._source_snapshot(repo / ".git", repo="example/project", sha=sha)

    assert snapshot["source_count"] == 1
    assert list(snapshot["sources"]) == ["src/core.py"]
    assert snapshot["source_projection"] == "frozen_candidate_path_filter_and_locked_candidate_python_suffix"


def test_production_diff_disables_rename_detection_and_excludes_oracle_surfaces(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "old_name.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests" / "test_old.py").write_text("def test_old():\n    assert True\n", encoding="utf-8")
    base_sha = _commit(repo, "baseline")

    (repo / "src" / "old_name.py").rename(repo / "src" / "new_name.py")
    (repo / "tests" / "test_old.py").write_text("def test_old():\n    assert False\n", encoding="utf-8")
    head_sha = _commit(repo, "candidate")

    diff = materializer._production_diff(repo / ".git", base_sha=base_sha, head_sha=head_sha)

    assert diff["changed_paths"] == ["src/new_name.py", "src/old_name.py"]
    assert "tests/test_old.py" not in diff["changed_paths"]
    assert diff["rename_policy"] == "disabled_decompose_to_delete_add"
    assert "deleted file mode" in diff["unified_diff"]
    assert "new file mode" in diff["unified_diff"]


def test_artifact_validator_rejects_path_traversal(tmp_path: Path) -> None:
    findings: list[str] = []
    result = _artifact_path(tmp_path, "../outside.json", findings, label="descriptor")
    assert result is None
    assert findings == ["descriptor must not escape the artifact root: ../outside.json"]
