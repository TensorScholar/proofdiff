from __future__ import annotations

import random

from proofdiff.engine.canonical import digest
from proofdiff.engine.diff import compare_manifests


def test_digest_is_independent_of_mapping_insertion_order() -> None:
    rng = random.Random(41)
    items = [(f"k{index}", index) for index in range(100)]
    reference = digest(dict(items))
    for _ in range(100):
        shuffled = items[:]
        rng.shuffle(shuffled)
        assert digest(dict(shuffled)) == reference


def test_identical_manifests_never_emit_changes() -> None:
    rng = random.Random(17)
    for index in range(100):
        manifest = {
            "agent": {"name": f"agent-{index}"},
            "runtime": {"model": f"m-{rng.randrange(5)}"},
            "tools": [
                {
                    "name": f"tool-{rng.randrange(10)}",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        }
        assert compare_manifests(manifest, manifest).is_empty
