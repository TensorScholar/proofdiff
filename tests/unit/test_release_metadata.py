from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from proofdiff._version import __version__

ROOT = Path(__file__).parents[2]


def test_version_metadata_is_consistent() -> None:
    assert __version__ in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"version: {__version__}" in (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    action = (ROOT / ".github" / "actions" / "proofdiff" / "action.yml").read_text(encoding="utf-8")
    assert "${{ github.action_path }}/../../.." in action
    assert "pip install --disable-pip-version-check \"proofdiff==" not in action


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
