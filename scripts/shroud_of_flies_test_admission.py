"""Byte-bound admission of the source-linked Shroud of Flies shooting regressions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,  # pyright: ignore[reportPrivateUsage]
    _selection_no_links,  # pyright: ignore[reportPrivateUsage]
    _selection_object,  # pyright: ignore[reportPrivateUsage]
)
from scripts.milli_inch_test_admission import MANIFEST, RETAINED_CUTOVER_SHA256
from scripts.stage3_defender_coherency_test_admission import RECEIPT_SHA256 as DEFENDER_SHA256

RECEIPT = "data/source_audits/ci64_provenance_v1/shroud-of-flies-test-v1.json"
RECEIPT_SHA256 = "5d2478c514160ce1a7eeb0499e13b8e3d256a03ffeecc7b126c8023dc8ee02b4"
BASE = "e5f2e9d94bbcd99d432d9a4441cbfbd63d564cf3"
OWNER = "tests/rules/section10/test_shooting_types.py"
PARSER_SOURCES = tuple(
    f"src/warhammer40k_core/rules/{name}"
    for name in (
        "aura_parser.py",
        "rule_duration_parser.py",
        "rule_keyword_sequences.py",
        "rule_parser.py",
    )
)
CASES = ("in_range", "out_of_range", "wrong_patron", "wrong_faction", "enemy", "destroyed")


class ShroudOfFliesReceipt(TypedDict):
    schema: str
    base: str
    retained_defender_sha256: str
    retained_cutover_sha256: str
    runtime_manifest: dict[str, str]
    runtime_fingerprint: dict[str, str]
    sources: dict[str, str]
    test: dict[str, dict[str, object]]
    added_cases: list[str]


def shroud_of_flies_test_successor(
    root: Path,
) -> tuple[ShroudOfFliesReceipt, bytes] | None:
    from scripts.build_test_shards import CUTOVER_PATH
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    _selection_no_links(root, root / RECEIPT)
    if not (root / RECEIPT).exists():
        return None
    raw = _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    receipt = cast(ShroudOfFliesReceipt, json.loads(raw, object_pairs_hook=_selection_object))
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, RETAINED_CUTOVER_SHA256),
        object_pairs_hook=_selection_object,
    )
    if (
        receipt.keys() != ShroudOfFliesReceipt.__required_keys__
        or receipt["schema"] != "finite-shroud-of-flies-test-v1"
        or receipt["base"] != BASE
        or receipt["retained_defender_sha256"] != DEFENDER_SHA256
        or receipt["retained_cutover_sha256"] != RETAINED_CUTOVER_SHA256
        or receipt["sources"].keys() != set(PARSER_SOURCES)
        or receipt["test"].keys() != {"before", "after"}
        or receipt["test"]["before"] != cutover["active_files"][OWNER]
        or receipt["test"]["before"] == receipt["test"]["after"]
        or receipt["added_cases"]
        != [
            f"{OWNER}::test_shroud_of_flies_grants_live_stealth_in_native_shooting[{c}]"
            for c in CASES
        ]
        or any(
            change.keys() != {"before", "after"} or change["before"] == change["after"]
            for change in (receipt["runtime_manifest"], receipt["runtime_fingerprint"])
        )
    ):
        raise SystemExit("Shroud of Flies test admission inventory differs.")
    manifest = _checked_bytes(root, MANIFEST, receipt["runtime_manifest"]["after"])
    if (
        json.loads(manifest, object_pairs_hook=_selection_object)["fingerprint"]
        != (receipt["runtime_fingerprint"]["after"])
    ):
        raise SystemExit("Shroud of Flies current runtime fingerprint differs from its manifest.")
    for path, digest in receipt["sources"].items():
        _checked_bytes(root, path, digest)
    _selection_members({OWNER: receipt["test"]["after"]}, root)
    return receipt, raw


def shroud_of_flies_runtime(
    root: Path, manifest_sha256: str, runtime_fingerprint: str
) -> tuple[str, str]:
    successor = shroud_of_flies_test_successor(root)
    if successor is None:
        return manifest_sha256, runtime_fingerprint
    receipt, _ = successor
    manifest = receipt["runtime_manifest"]
    fingerprint = receipt["runtime_fingerprint"]
    if (manifest["before"], fingerprint["before"]) != (manifest_sha256, runtime_fingerprint):
        raise SystemExit("Shroud of Flies tests require the exact defender coherency runtime.")
    return manifest["after"], fingerprint["after"]
