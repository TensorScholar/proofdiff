from __future__ import annotations

import re
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from scripts import build_dist

from proofdiff._version import __version__

ROOT = Path(__file__).parents[2]


def test_version_metadata_is_consistent() -> None:
    assert __version__ in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"version: {__version__}" in (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    action = (ROOT / ".github" / "actions" / "proofdiff" / "action.yml").read_text(encoding="utf-8")
    assert "${{ github.action_path }}/../../.." in action
    assert 'pip install --disable-pip-version-check "proofdiff==' not in action


def test_workflows_and_action_are_valid_yaml() -> None:
    paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    paths.append(ROOT / ".github" / "actions" / "proofdiff" / "action.yml")
    for path in paths:
        assert isinstance(yaml.safe_load(path.read_text(encoding="utf-8")), dict)


def test_external_github_actions_are_pinned_to_full_sha() -> None:
    pattern = re.compile(r"^\s*- uses: ([^\s@]+)@([^\s#]+)", re.MULTILINE)
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for action, ref in pattern.findall(path.read_text(encoding="utf-8")):
            if action.startswith("./"):
                continue
            assert re.fullmatch(r"[0-9a-f]{40}", ref), f"unpinned action {action}@{ref} in {path}"


def test_svg_assets_are_well_formed() -> None:
    for path in sorted((ROOT / "docs" / "assets").glob("*.svg")):
        root = ET.parse(path).getroot()
        assert root.tag.endswith("svg")


def test_readme_stays_focused() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert len(readme.splitlines()) <= 240
    assert "What ProofDiff is not" in readme
    assert "not claims about production workloads" in readme


def test_deterministic_wheel_uses_valid_license_metadata_version() -> None:
    metadata_files = {
        path: data.decode("utf-8") for path, data in build_dist.wheel_metadata().items() if path.endswith("/METADATA")
    }
    assert len(metadata_files) == 1
    metadata = next(iter(metadata_files.values()))
    assert metadata.startswith("Metadata-Version: 2.4\n")
    assert "License-Expression: Apache-2.0\n" in metadata


def test_deterministic_sdist_contains_pkg_info(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(build_dist, "DIST", tmp_path)
    sdist = build_dist.build_sdist()

    with tarfile.open(sdist, "r:gz") as archive:
        member = archive.extractfile(f"proofdiff-{__version__}/PKG-INFO")
        assert member is not None
        pkg_info = member.read()

    expected = next(data for path, data in build_dist.wheel_metadata().items() if path.endswith("/METADATA"))
    assert pkg_info == expected


def test_deterministic_sdist_excludes_local_build_artifacts() -> None:
    excluded = (
        Path("src/proofdiff.egg-info/PKG-INFO"),
        Path("venv/bin/python"),
        Path(".venv/bin/python"),
        Path(".proofdiff/evidence/decision.json"),
        Path(".DS_Store"),
        Path("src/proofdiff/__pycache__/x.pyc"),
    )
    for path in excluded:
        assert not build_dist.include_in_sdist(path)

    assert build_dist.include_in_sdist(Path("src/proofdiff/__init__.py"))
