from __future__ import annotations

import re
import tarfile
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest
import yaml
from scripts import build_dist, check_release, smoke_install

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


@pytest.fixture(scope="module")
def canonical_distributions(tmp_path_factory: pytest.TempPathFactory) -> build_dist.DistributionSet:
    return build_dist.build_distributions(tmp_path_factory.mktemp("canonical-dist"))


def wheel_metadata(wheel: Path):
    with zipfile.ZipFile(wheel) as archive:
        metadata_paths = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        assert len(metadata_paths) == 1
        return BytesParser(policy=policy.default).parsebytes(archive.read(metadata_paths[0]))


def test_canonical_wheel_metadata_comes_from_pyproject(canonical_distributions: build_dist.DistributionSet) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    metadata = wheel_metadata(canonical_distributions.wheel)
    assert metadata["Name"] == project["name"]
    assert metadata["Version"] == __version__
    assert metadata["Summary"] == project["description"]
    assert metadata["Project-URL"] == f"Homepage, {project['urls']['Homepage']}"
    assert f"Issues, {project['urls']['Issues']}" in metadata.get_all("Project-URL", [])


def test_canonical_wheel_declares_yaml_extra(canonical_distributions: build_dist.DistributionSet) -> None:
    metadata = wheel_metadata(canonical_distributions.wheel)
    assert "yaml" in metadata.get_all("Provides-Extra", [])
    requirements = {requirement.replace(" ", "").lower() for requirement in metadata.get_all("Requires-Dist", [])}
    assert 'pyyaml>=6.0;extra=="yaml"' in requirements


def test_canonical_build_emits_exactly_one_wheel_and_sdist(
    canonical_distributions: build_dist.DistributionSet,
) -> None:
    assert {
        path.name for path in canonical_distributions.output_dir.iterdir()
    } == build_dist.expected_distribution_names()


def test_sdist_contains_documented_runnable_example_helpers(
    canonical_distributions: build_dist.DistributionSet,
) -> None:
    prefix = f"proofdiff-{__version__}/"
    with tarfile.open(canonical_distributions.sdist, "r:gz") as archive:
        names = set(archive.getnames())
    assert prefix + "src/proofdiff/cli/main.py" in names
    assert prefix + "examples/agentguard-mcp-exit-race/prepare.py" in names
    assert prefix + "examples/agentguard-mcp-exit-race/verify.py" in names


def test_checksum_manifest_covers_every_public_asset(
    canonical_distributions: build_dist.DistributionSet, tmp_path: Path
) -> None:
    for source in (canonical_distributions.wheel, canonical_distributions.sdist):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    (tmp_path / build_dist.SBOM_NAME).write_text("{}\n", encoding="utf-8")
    checksum = build_dist.write_checksum_manifest(tmp_path)
    build_dist.verify_checksum_manifest(tmp_path)
    covered = {line.partition("  ")[2] for line in checksum.read_text(encoding="utf-8").splitlines()}
    assert covered == build_dist.expected_public_asset_names()
    assert build_dist.CHECKSUM_NAME not in covered


def test_invalid_tag_version_mismatch_fails() -> None:
    mismatched_tag = "v0.0.0" if __version__ != "0.0.0" else "v999.0.0"
    with pytest.raises(SystemExit, match="tag/version mismatch"):
        check_release.check_version_consistency(mismatched_tag)


def test_current_tag_version_matches() -> None:
    check_release.check_version_consistency(f"v{__version__}")


def test_clean_canonical_wheel_smoke_install(canonical_distributions: build_dist.DistributionSet) -> None:
    smoke_install.smoke_install(canonical_distributions.wheel)
