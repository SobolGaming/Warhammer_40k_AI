"""Byte-bound admission of the native Fortification regressions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

from scripts.behavioral_selection_members import (
    _selection_members,  # pyright: ignore[reportPrivateUsage]
    _selection_no_links,  # pyright: ignore[reportPrivateUsage]
    _selection_object,  # pyright: ignore[reportPrivateUsage]
)
from scripts.milli_inch_test_admission import MANIFEST

RECEIPT = "data/source_audits/ci64_provenance_v1/fortification-engagement-test-v1.json"
RECEIPT_SHA256 = "aaa5fe2e0078d0b63ed6bd67b01cd3e4c4369a2460045695a9c5201de4a4a7be"
BASE = "767c5f2a09f10ec1fe6216ac2c3785fe12f48670"
ROTATION_RECEIPT = "data/source_audits/ci64_provenance_v1/fortification-rotation-test-v1.json"
ROTATION_RECEIPT_SHA256 = "13d8d42dfc5f317238e78ebe1f978b21c1b77c88dc41d56a20f6a6139cb54d20"
ROTATION_BASE = "2a5bb77fd6eb1a04c276037ea159a5ef850f1668"
ROTATION_SOURCES = {
    "src/warhammer40k_core/engine/phases/movement_geometry.py",
    "src/warhammer40k_core/geometry/physical_predicates.py",
}
OWNER = "tests/rules/section09/test_fortification_engagement.py"
SOURCES = frozenset(
    {
        "src/warhammer40k_core/engine/catalog_contextual_status_consumption.py",
        "src/warhammer40k_core/engine/desperate_escape_mortal_wounds.py",
        "src/warhammer40k_core/engine/movement_decision_authority.py",
        "src/warhammer40k_core/engine/phases/movement_escape_mortals.py",
        "src/warhammer40k_core/engine/phases/movement_geometry.py",
        "src/warhammer40k_core/engine/phases/movement_options_dice.py",
        "src/warhammer40k_core/engine/phases/movement_resolution_flow.py",
        "src/warhammer40k_core/engine/phases/movement_resolvers.py",
        "src/warhammer40k_core/engine/phases/movement_rules_units.py",
        "src/warhammer40k_core/engine/phases/movement_validation.py",
        "src/warhammer40k_core/engine/shooting_targets.py",
        "src/warhammer40k_core/geometry/physical_predicates.py",
        "src/warhammer40k_core/rules/rule_parser_selected_target_extensions.py",
        "src/warhammer40k_core/rules/specialized_rule_parser.py",
        "tests/support/fortification_fixtures.py",
    }
)


TERROR_SOURCE_SUCCESSORS = frozenset(
    {
        "src/warhammer40k_core/engine/movement_decision_authority.py",
        "src/warhammer40k_core/engine/phases/movement_escape_mortals.py",
    }
)


class FortificationTestReceipt(TypedDict):
    schema: str
    base: str
    retained_shroud_sha256: str
    historical_sources: dict[str, dict[str, str]]
    runtime_manifest: dict[str, str]
    runtime_fingerprint: dict[str, str]
    sources: dict[str, str]
    added_files: dict[str, dict[str, object]]
    added_cases: list[str]


class FortificationRotationReceipt(TypedDict):
    schema: str
    base: str
    retained_fortification_sha256: str
    runtime_manifest: dict[str, str]
    runtime_fingerprint: dict[str, str]
    sources: dict[str, dict[str, str]]
    test: dict[str, dict[str, object]]
    added_cases: list[str]


def _fortification_rotation_successor(
    root: Path,
    previous: FortificationTestReceipt,
) -> tuple[FortificationTestReceipt, bytes] | None:
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    path = root / ROTATION_RECEIPT
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, ROTATION_RECEIPT, ROTATION_RECEIPT_SHA256)
    receipt = cast(
        FortificationRotationReceipt, json.loads(raw, object_pairs_hook=_selection_object)
    )
    additions = receipt["added_cases"]
    if (
        receipt.keys() != FortificationRotationReceipt.__required_keys__
        or receipt["schema"] != "finite-fortification-rotation-test-v1"
        or receipt["base"] != ROTATION_BASE
        or receipt["retained_fortification_sha256"] != RECEIPT_SHA256
        or receipt["sources"].keys() != ROTATION_SOURCES
        or receipt["test"].keys() != {"before", "after"}
        or receipt["test"]["before"] != previous["added_files"][OWNER]
        or receipt["test"]["before"] == receipt["test"]["after"]
        or len(additions) != 5
        or len(set(additions)) != 5
        or set(additions).intersection(previous["added_cases"])
        or any(not node.startswith(f"{OWNER}::") for node in additions)
        or any(
            change.keys() != {"before", "after"}
            or change["before"] != old_digest
            or change["after"] == old_digest
            for change, old_digest in (
                (receipt["runtime_manifest"], previous["runtime_manifest"]["after"]),
                (receipt["runtime_fingerprint"], previous["runtime_fingerprint"]["after"]),
                *(
                    (change, previous["sources"][name])
                    for name, change in receipt["sources"].items()
                ),
            )
        )
    ):
        raise SystemExit("Fortification rotation differs from the exact predecessor.")
    current: FortificationTestReceipt = {
        **previous,
        "runtime_manifest": {
            **previous["runtime_manifest"],
            "after": receipt["runtime_manifest"]["after"],
        },
        "runtime_fingerprint": {
            **previous["runtime_fingerprint"],
            "after": receipt["runtime_fingerprint"]["after"],
        },
        "sources": {
            **previous["sources"],
            **{name: change["after"] for name, change in receipt["sources"].items()},
        },
        "added_files": {OWNER: receipt["test"]["after"]},
        "added_cases": [*previous["added_cases"], *additions],
    }
    return current, raw


def _fortification_receipt(root: Path) -> tuple[FortificationTestReceipt, bytes] | None:
    from scripts.engine_numerical_identity_test_admission import (
        DAEMONIC_TERROR_TRANSITION_SHA256,
        GORE_HUNGRY_ONSLAUGHT_SHA256,
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    path = root / RECEIPT
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, RECEIPT, RECEIPT_SHA256)
    receipt = cast(FortificationTestReceipt, json.loads(raw, object_pairs_hook=_selection_object))
    historical_owners = {
        DAEMONIC_TERROR_TRANSITION_SHA256: TERROR_SOURCE_SUCCESSORS,
        GORE_HUNGRY_ONSLAUGHT_SHA256: frozenset(
            {"src/warhammer40k_core/engine/phases/movement_resolution_flow.py"}
        ),
    }
    if (
        receipt.keys() != FortificationTestReceipt.__required_keys__
        or receipt["schema"] != "finite-fortification-engagement-test-v1"
        or receipt["base"] != BASE
        or receipt["historical_sources"].keys() != historical_owners.keys()
        or any(
            receipt["historical_sources"][sha256].keys() != expected
            for sha256, expected in historical_owners.items()
        )
        or receipt["sources"].keys() != SOURCES
    ):
        raise SystemExit("Fortification test admission source inventory differs.")
    return receipt, raw


def fortification_historical_source_successors(
    root: Path, *, previous_sha256: str, previous_sources: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Admit current owner bytes against the exact historical receipt that pinned them."""
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    loaded = _fortification_receipt(root)
    if loaded is None:
        return {}
    receipt, _ = loaded
    historical = receipt["historical_sources"].get(previous_sha256)
    if historical is None or any(
        name not in previous_sources or previous_sources[name]["after"] != before
        for name, before in historical.items()
    ):
        raise SystemExit("Fortification retry source preimage differs from its historical receipt.")
    successors = {}
    for name, before in historical.items():
        after = receipt["sources"][name]
        if before == after:
            raise SystemExit("Fortification retry source successor did not change: " + name)
        _checked_bytes(root, name, after)
        successors[name] = {"before": before, "after": after}
    return successors


def fortification_test_addition(
    root: Path,
    *,
    predecessor_manifest: str,
    predecessor_fingerprint: str,
) -> tuple[FortificationTestReceipt, dict[str, dict[str, object]], bytes] | None:
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )
    from scripts.shroud_of_flies_test_admission import RECEIPT_SHA256 as SHROUD_SHA256

    loaded = _fortification_receipt(root)
    if loaded is None:
        return None
    receipt, raw = loaded
    if (
        receipt["retained_shroud_sha256"] != SHROUD_SHA256
        or receipt["added_files"].keys() != {OWNER}
        or len(receipt["added_cases"]) != 17
        or len(set(receipt["added_cases"])) != 17
        or any(not node.startswith(f"{OWNER}::") for node in receipt["added_cases"])
        or any(
            change.keys() != {"before", "after"} or change["before"] == change["after"]
            for change in (receipt["runtime_manifest"], receipt["runtime_fingerprint"])
        )
        or receipt["runtime_manifest"]["before"] != predecessor_manifest
        or receipt["runtime_fingerprint"]["before"] != predecessor_fingerprint
    ):
        raise SystemExit("Fortification test admission differs from the exact Shroud predecessor.")
    rotation = _fortification_rotation_successor(root, receipt)
    if rotation is not None:
        receipt, rotation_raw = rotation
        raw += b"\0" + rotation_raw
    manifest = _checked_bytes(root, MANIFEST, receipt["runtime_manifest"]["after"])
    if (
        json.loads(manifest, object_pairs_hook=_selection_object)["fingerprint"]
        != (receipt["runtime_fingerprint"]["after"])
    ):
        raise SystemExit("Fortification runtime fingerprint differs from its manifest.")
    for name, digest in receipt["sources"].items():
        _checked_bytes(root, name, digest)
    return receipt, _selection_members(receipt["added_files"], root), raw
