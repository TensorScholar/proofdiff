from __future__ import annotations

import pytest

from proofdiff.domain.errors import InputError
from proofdiff.engine.canonical import canonical_bytes, digest, normalize, redact_secrets


def test_canonical_order_is_stable() -> None:
    left = {"b": 2, "a": {"y": 1, "x": [3, 2, 1]}}
    right = {"a": {"x": [3, 2, 1], "y": 1}, "b": 2}
    assert canonical_bytes(left) == canonical_bytes(right)
    assert digest(left) == digest(right)


def test_non_finite_number_rejected() -> None:
    with pytest.raises(InputError):
        normalize({"score": float("nan")})


def test_secret_fields_are_redacted_recursively() -> None:
    value = {"api_key": "abc", "nested": {"refreshToken": "unsafe", "ok": 1}}
    assert redact_secrets(value) == {
        "api_key": "<redacted>",
        "nested": {"refreshToken": "<redacted>", "ok": 1},
    }
