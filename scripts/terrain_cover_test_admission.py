"""Byte-bound admission of the exact terrain cover regressions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,  # pyright: ignore[reportPrivateUsage]
    _selection_no_links,  # pyright: ignore[reportPrivateUsage]
    _selection_object,  # pyright: ignore[reportPrivateUsage]
)
from scripts.milli_inch_test_admission import RETAINED_CUTOVER_SHA256

RECEIPT = "data/source_audits/ci64_provenance_v1/exact-terrain-cover-test-v1.json"
RECEIPT_SHA256 = "8efd0a5728e4a54e30579208af05ba18c92f07f8e29fc8453dcf2746197237ee"
BASE = "c61269d843e6fce49afb6ed3618e988e03d8baff"
OWNER = "tests/rules/section13/test_visibility.py"
SOURCES = (
    "src/warhammer40k_core/core/visibility.py",
    "src/warhammer40k_core/geometry/visibility_occlusion.py",
)
CASES = (
    "test_cover_attribution_preserves_causal_sources[independent]",
    "test_cover_attribution_preserves_causal_sources[joint-only]",
    "test_cover_attribution_preserves_causal_sources[incidental]",
    "test_cover_attribution_preserves_a_contained_observer",
    "test_cover_attribution_chooses_exact_visibility_masks[separated]",
    "test_cover_attribution_chooses_exact_visibility_masks[touching]",
)


class TerrainCoverTestReceipt(TypedDict):
    schema: str
    base: str
    retained_fortification_sha256: str
    retained_cutover_sha256: str
    runtime_manifest: dict[str, str]
    runtime_fingerprint: dict[str, str]
    sources: dict[str, dict[str, str]]
    test: dict[str, dict[str, object]]
    added_cases: list[str]


def terrain_cover_test_successor(root: Path) -> tuple[TerrainCoverTestReceipt, bytes] | None:
    from scripts.build_test_shards import CUTOVER_PATH
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    _selection_no_links(root, root / RECEIPT)
    if not (root / RECEIPT).exists():
        return None
    raw = _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    receipt = cast(TerrainCoverTestReceipt, json.loads(raw, object_pairs_hook=_selection_object))
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, RETAINED_CUTOVER_SHA256),
        object_pairs_hook=_selection_object,
    )
    if (
        receipt.keys() != TerrainCoverTestReceipt.__required_keys__
        or receipt["schema"] != "finite-exact-terrain-cover-test-v1"
        or receipt["base"] != BASE
        or receipt["retained_cutover_sha256"] != RETAINED_CUTOVER_SHA256
        or receipt["added_cases"] != [f"{OWNER}::{name}" for name in CASES]
        or receipt["test"].keys() != {"before", "after"}
        or receipt["test"]["before"] != cutover["active_files"][OWNER]
        or receipt["test"]["before"] == receipt["test"]["after"]
        or receipt["sources"].keys() != set(SOURCES)
        or any(
            change.keys() != {"before", "after"} or change["before"] == change["after"]
            for change in (
                receipt["runtime_manifest"],
                receipt["runtime_fingerprint"],
                *receipt["sources"].values(),
            )
        )
    ):
        raise SystemExit("Exact terrain cover test admission inventory differs.")
    for path, change in receipt["sources"].items():
        _checked_bytes(root, path, change["after"])
    _selection_members({OWNER: receipt["test"]["after"]}, root)
    return receipt, raw
