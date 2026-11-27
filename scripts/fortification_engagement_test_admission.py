"""Byte-bound admission of the native Fortification regressions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple, TypedDict, cast

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
RETRY_RECEIPT = "data/source_audits/ci64_provenance_v1/fortification-survivor-retry-test-v1.json"
RETRY_RECEIPT_SHA256 = "68735efb653722f33d34525bd2fe85fca4ea543e7dde169b65498ba7547d197b"
RETRY_BASE = "6b6ba4bbf412d4b3b62ba91562c8476cbbb344b1"
DEVELOPMENT_RECEIPT = "data/source_audits/ci64_provenance_v1/gnarlmaw-development-test-v1.json"
DEVELOPMENT_RECEIPT_SHA256 = "c08d2e6861d2e552cdb012a66e94f668fd3d1ee6302105240dfc4cdaf52a2158"
DEVELOPMENT_BASE = "73d8de5e163908c832cad7d6a2fd5428ed7d9c80"
DEVELOPMENT_PREIMAGES = {
    "src/warhammer40k_core/engine/attack_sequence_hazardous.py": (
        "fd0ca164bfe944b2d0d526d67bf1c2271128ec2b0d2f396ad156bc13bba89c98"
    ),
    "src/warhammer40k_core/engine/deployment_geometry.py": (
        "e3eb1851835eeef4f0b88bf443cf74fcd47257e7024fb06044777c602145deee"
    ),
}
ALLOCATION_RECEIPT = "data/source_audits/ci64_provenance_v1/gnarlmaw-allocation-test-v1.json"
ALLOCATION_RECEIPT_SHA256 = "f55d16d2594073381a50616806ddf5358d9f75be2cdad1d98a45e6b5db9b3935"
ALLOCATION_BASE = "f106e9d80b7d9170bdf08c6cad8189dcdff8e169"
ALLOCATION_PREIMAGES = {
    "src/warhammer40k_core/engine/ability_coverage.py": (
        "01f751c83cfcc153547830ee37f304b0e1d9479bbd855f1d6ddbc313d35c216d"
    ),
}
TYPING_RECEIPT = "data/source_audits/ci64_provenance_v1/gnarlmaw-test-typing-v1.json"
TYPING_RECEIPT_SHA256 = "3edf827ba489182f3522315588789e03b22957a047887195dc36ec976c94c01d"
TYPING_BASE = "e8f79d797aa99c1f4e40b1609df7580a480bb3f2"
TYPING_INACTIVE_OWNER = "tests/unit/test_skull_altar_runtime_regressions.py"
CATALOG_SOURCE_RECEIPT = "data/source_audits/ci64_provenance_v1/gnarlmaw-source-test-v1.json"
CATALOG_SOURCE_RECEIPT_SHA256 = "5e395e78befc9c49490658852563516e3da2d144f8d6b9e3e6ec4966fdb3f7e3"
CATALOG_SOURCE_BASE = "dffa47e8ab1d8243028c878da4a7a28a3b843c6d"
GNARLMAW_PACKAGE_PATH = (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "chaos_daemons_gnarlmaw_2026_11"
)
CATALOG_SOURCE_PREIMAGES = {
    f"{GNARLMAW_PACKAGE_PATH}/__init__.py": (
        "01efb3ac32057e2c1784f43082f094908d8fc5ed5b4ba32d2248b3bc7915baa5"
    ),
    f"{GNARLMAW_PACKAGE_PATH}/artifacts/catalog.json": (
        "15864f07cf2a3a0d179cf43f74f5b4b8a712748c388566d1f70b0cffc25e329a"
    ),
}
PRE_HIT_COVER_RECEIPT = "data/source_audits/ci64_provenance_v1/gnarlmaw-pre-hit-cover-test-v1.json"
PRE_HIT_COVER_RECEIPT_SHA256 = "19d00acf6fac25c07e4e7953626425f049edbb5af414a776581a95ada1ca5aac"
PRE_HIT_COVER_BASE = "7f157a5aae0cd289430f794615d0ebb05e074aca"
PRE_HIT_COVER_PREIMAGES = {
    "src/warhammer40k_core/engine/ability_coverage.py": (
        "2ae0a9cfb06f4b03c03184627b0198294edba799e378071af06feabe662754eb"
    ),
    "src/warhammer40k_core/engine/attack_modifier_snapshots.py": (
        "baa4aa7e63014cf75b675fed541b90e301b37c07133981a86a5a4417784e9192"
    ),
    "src/warhammer40k_core/engine/attack_sequence_group_selection.py": (
        "f9a8846b62b5879589c98b38dbe572c585194d2a976888c4a7421e3a66176db9"
    ),
    "src/warhammer40k_core/engine/attack_sequence_hazardous.py": (
        "45f2b0f2485b5c1cbb78c1f86fb5768e320ac8db51bbbb14e24c1f1ef926ba35"
    ),
    "src/warhammer40k_core/engine/attack_sequence_hit_wound.py": (
        "d677e50e2bf25c4bb852e9f131a2f1b4b797e5a51a6ec85808b9e32a3070db69"
    ),
    "src/warhammer40k_core/engine/native_gathering_cover_rules.py": (
        "66a976554ff0398ba2f1dbbf88d329d31eec4713e9716582ae8db20d3546e1bc"
    ),
    f"{GNARLMAW_PACKAGE_PATH}/__init__.py": (
        "09ea0fabc13ca2cc53c00a02d3f5a88327ba7737a27e182842decd81a2dd106c"
    ),
}
ROTATION_SOURCES = {
    "src/warhammer40k_core/engine/phases/movement_geometry.py",
    "src/warhammer40k_core/geometry/physical_predicates.py",
}
RETRY_PREIMAGES = {
    "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py": (
        "54092610a2f236c9400b03c42d09de5cfa6338ba10338cc967a22352bbefc296"
    ),
}
RETRY_SOURCES = {
    *RETRY_PREIMAGES,
    "src/warhammer40k_core/engine/phases/movement_escape_mortals.py",
    "src/warhammer40k_core/engine/phases/movement_geometry.py",
    "src/warhammer40k_core/engine/phases/movement_resolution_flow.py",
    "src/warhammer40k_core/engine/phases/movement_rules_units.py",
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


class FortificationSuccessorReceipt(TypedDict):
    schema: str
    base: str
    retained_fortification_sha256: str
    runtime_manifest: dict[str, str]
    runtime_fingerprint: dict[str, str]
    sources: dict[str, dict[str, str]]
    test: dict[str, dict[str, object]]
    added_cases: list[str]


class _Successor(NamedTuple):
    path: str
    sha256: str
    base: str
    schema: str
    prior_sha256: str
    added_count: int
    sources: set[str]
    additional_preimages: dict[str, str]


def _fortification_successor(
    root: Path,
    previous: FortificationTestReceipt,
    transition: _Successor,
) -> tuple[FortificationTestReceipt, bytes] | None:
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    path = root / transition.path
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, transition.path, transition.sha256)
    receipt = cast(
        FortificationSuccessorReceipt, json.loads(raw, object_pairs_hook=_selection_object)
    )
    keys = FortificationSuccessorReceipt.__required_keys__
    if transition.path == TYPING_RECEIPT:
        keys = keys | {"inactive_test"}
    additions = receipt["added_cases"]
    source_preimages = {**previous["sources"], **transition.additional_preimages}
    if (
        receipt.keys() != keys
        or receipt["schema"] != transition.schema
        or receipt["base"] != transition.base
        or receipt["retained_fortification_sha256"] != transition.prior_sha256
        or receipt["sources"].keys() != transition.sources
        or receipt["test"].keys() != {"before", "after"}
        or receipt["test"]["before"] != previous["added_files"][OWNER]
        or receipt["test"]["before"] == receipt["test"]["after"]
        or len(additions) != transition.added_count
        or len(set(additions)) != transition.added_count
        or set(additions).intersection(previous["added_cases"])
        or any(not node.startswith(f"{OWNER}::") for node in additions)
        or any(
            change.keys() != {"before", "after"}
            or change["before"] != old_digest
            or (change["after"] != old_digest) != bool(transition.sources)
            for change, old_digest in (
                (receipt["runtime_manifest"], previous["runtime_manifest"]["after"]),
                (receipt["runtime_fingerprint"], previous["runtime_fingerprint"]["after"]),
                *((change, source_preimages[name]) for name, change in receipt["sources"].items()),
            )
        )
    ):
        raise SystemExit("Fortification successor differs from the exact predecessor.")
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


def _fortification_current_receipt(
    root: Path, receipt: FortificationTestReceipt, raw: bytes
) -> tuple[FortificationTestReceipt, bytes]:
    rotation = _fortification_successor(
        root,
        receipt,
        _Successor(
            ROTATION_RECEIPT,
            ROTATION_RECEIPT_SHA256,
            ROTATION_BASE,
            "finite-fortification-rotation-test-v1",
            RECEIPT_SHA256,
            5,
            ROTATION_SOURCES,
            {},
        ),
    )
    if rotation is None:
        if (root / RETRY_RECEIPT).exists():
            raise SystemExit("Fortification survivor retry requires its rotation predecessor.")
        return receipt, raw
    receipt, successor_raw = rotation
    raw += b"\0" + successor_raw
    retry = _fortification_successor(
        root,
        receipt,
        _Successor(
            RETRY_RECEIPT,
            RETRY_RECEIPT_SHA256,
            RETRY_BASE,
            "finite-fortification-survivor-retry-test-v1",
            ROTATION_RECEIPT_SHA256,
            1,
            RETRY_SOURCES,
            RETRY_PREIMAGES,
        ),
    )
    if retry is None:
        if (root / DEVELOPMENT_RECEIPT).exists():
            raise SystemExit(
                "Gnarlmaw development requires the exact Fortification retry predecessor."
            )
        return receipt, raw
    receipt, successor_raw = retry
    raw += b"\0" + successor_raw
    development = _fortification_successor(
        root,
        receipt,
        _Successor(
            DEVELOPMENT_RECEIPT,
            DEVELOPMENT_RECEIPT_SHA256,
            DEVELOPMENT_BASE,
            "finite-gnarlmaw-development-test-v1",
            RETRY_RECEIPT_SHA256,
            2,
            set(DEVELOPMENT_PREIMAGES),
            DEVELOPMENT_PREIMAGES,
        ),
    )
    if development is None:
        if (root / ALLOCATION_RECEIPT).exists():
            raise SystemExit("Gnarlmaw allocation requires the exact development predecessor.")
        return receipt, raw
    receipt, successor_raw = development
    raw += b"\0" + successor_raw
    allocation = _fortification_successor(
        root,
        receipt,
        _Successor(
            ALLOCATION_RECEIPT,
            ALLOCATION_RECEIPT_SHA256,
            ALLOCATION_BASE,
            "finite-gnarlmaw-allocation-test-v1",
            DEVELOPMENT_RECEIPT_SHA256,
            1,
            set(ALLOCATION_PREIMAGES),
            ALLOCATION_PREIMAGES,
        ),
    )
    if allocation is None:
        if (root / TYPING_RECEIPT).exists():
            raise SystemExit("Gnarlmaw test typing requires the exact allocation predecessor.")
        return receipt, raw
    receipt, successor_raw = allocation
    raw += b"\0" + successor_raw
    typing = _fortification_successor(
        root,
        receipt,
        _Successor(
            TYPING_RECEIPT,
            TYPING_RECEIPT_SHA256,
            TYPING_BASE,
            "finite-gnarlmaw-test-typing-v1",
            ALLOCATION_RECEIPT_SHA256,
            0,
            set(),
            {},
        ),
    )
    if typing is None:
        if (root / CATALOG_SOURCE_RECEIPT).exists():
            raise SystemExit("Gnarlmaw catalog sources require the exact typing predecessor.")
        return receipt, raw
    receipt, successor_raw = typing
    raw += b"\0" + successor_raw
    source = _fortification_successor(
        root,
        receipt,
        _Successor(
            CATALOG_SOURCE_RECEIPT,
            CATALOG_SOURCE_RECEIPT_SHA256,
            CATALOG_SOURCE_BASE,
            "finite-gnarlmaw-source-test-v1",
            TYPING_RECEIPT_SHA256,
            0,
            set(CATALOG_SOURCE_PREIMAGES),
            CATALOG_SOURCE_PREIMAGES,
        ),
    )
    if source is None:
        if (root / PRE_HIT_COVER_RECEIPT).exists():
            raise SystemExit("Gnarlmaw pre-Hit cover requires the exact catalog predecessor.")
        return receipt, raw
    receipt, successor_raw = source
    raw += b"\0" + successor_raw
    pre_hit_cover = _fortification_successor(
        root,
        receipt,
        _Successor(
            PRE_HIT_COVER_RECEIPT,
            PRE_HIT_COVER_RECEIPT_SHA256,
            PRE_HIT_COVER_BASE,
            "finite-gnarlmaw-pre-hit-cover-test-v1",
            CATALOG_SOURCE_RECEIPT_SHA256,
            7,
            set(PRE_HIT_COVER_PREIMAGES),
            PRE_HIT_COVER_PREIMAGES,
        ),
    )
    if pre_hit_cover is not None:
        receipt, successor_raw = pre_hit_cover
        raw += b"\0" + successor_raw
    return receipt, raw


def gnarlmaw_inactive_test_successor(
    root: Path, retained: dict[str, object]
) -> dict[str, dict[str, object]]:
    """Validate the shared cover helper repair in its existing inactive fixture."""
    from scripts.engine_numerical_identity_test_admission import (
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    path = root / TYPING_RECEIPT
    _selection_no_links(root, path)
    if not path.exists():
        return {}
    raw = _checked_bytes(root, TYPING_RECEIPT, TYPING_RECEIPT_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    row = record["inactive_test"]
    if (
        not isinstance(row, dict)
        or row.keys() != {"before", "after"}
        or row["before"] != retained.get(TYPING_INACTIVE_OWNER)
    ):
        raise SystemExit("Gnarlmaw inactive test preimage does not match retained membership.")
    return _selection_members({TYPING_INACTIVE_OWNER: row["after"]}, root)


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
        DAEMONIC_TERROR_TRANSITION_SHA256,
        _checked_bytes,  # pyright: ignore[reportPrivateUsage]
    )

    loaded = _fortification_receipt(root)
    if loaded is None:
        return {}
    receipt, raw = loaded
    historical = receipt["historical_sources"].get(previous_sha256)
    receipt, _ = _fortification_current_receipt(root, receipt, raw)
    if historical is None:
        raise SystemExit("Fortification retry source preimage differs from its historical receipt.")
    if previous_sha256 == DAEMONIC_TERROR_TRANSITION_SHA256 and RETRY_PREIMAGES.keys() <= (
        receipt["sources"].keys()
    ):
        historical = {**historical, **RETRY_PREIMAGES}
    if any(
        name not in previous_sources or previous_sources[name]["after"] != before
        for name, before in historical.items()
    ):
        raise SystemExit("Fortification retry source preimage differs from its historical receipt.")
    successors: dict[str, dict[str, str]] = {}
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
    receipt, raw = _fortification_current_receipt(root, receipt, raw)
    manifest = _checked_bytes(root, MANIFEST, receipt["runtime_manifest"]["after"])
    if (
        json.loads(manifest, object_pairs_hook=_selection_object)["fingerprint"]
        != (receipt["runtime_fingerprint"]["after"])
    ):
        raise SystemExit("Fortification runtime fingerprint differs from its manifest.")
    for name, digest in receipt["sources"].items():
        _checked_bytes(root, name, digest)
    return receipt, _selection_members(receipt["added_files"], root), raw
