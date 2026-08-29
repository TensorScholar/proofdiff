from __future__ import annotations

from pathlib import Path

import pytest

from proofdiff.domain.errors import VerificationError
from proofdiff.engine.evidence import verify_evidence_bundle


def test_verify_rejects_missing_and_invalid_checksum_files(tmp_path: Path) -> None:
    with pytest.raises(VerificationError, match="missing"):
        verify_evidence_bundle(tmp_path)

    (tmp_path / "checksums.txt").write_text("bad-line\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="invalid checksum"):
        verify_evidence_bundle(tmp_path)

    (tmp_path / "checksums.txt").write_text("0" * 64 + "  missing.json\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="evidence file is missing"):
        verify_evidence_bundle(tmp_path)

    (tmp_path / "checksums.txt").write_text("\n", encoding="utf-8")
    with pytest.raises(VerificationError, match="no entries"):
        verify_evidence_bundle(tmp_path)
