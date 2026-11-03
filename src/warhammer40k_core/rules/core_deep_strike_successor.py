"""Exact reviewed Deep Strike successors, projected before historical reconciliation."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from typing import Final

import msgspec

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet_ability import DatasheetAbilityDescriptor
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

ABILITY_ID: Final = "000008343"
SOURCE_ID: Final = "gw-11e-core-abilities:core:deep-strike"
DEPENDENCY_ID: Final = "gw-11e-core-reserve-lifetimes:ingress"
SUCCESSOR_ARTIFACT_SHA256: Final = (
    "2e4157da3a5dd00a3850d2c31294008a758a161b37e596745afc988ad9074b85"
)
_SOURCE_PACKAGE: Final = (
    "warhammer40k_core.rules.source_packages.warhammer_40000_11th."
    "core_deep_strike_description_2026_11"
)


class DeepStrikeSuccessorOccurrence(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    catalog_id: str
    datasheet_id: str
    historical_descriptor_sha256: str
    current_descriptor_sha256: str


class DeepStrikeSuccessorArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    schema: str
    ability_id: str
    source_id: str
    dependency_source_id: str
    historical_text: str
    current_text: str
    occurrences: tuple[DeepStrikeSuccessorOccurrence, ...]


def successor_from_json_bytes(raw: bytes) -> DeepStrikeSuccessorArtifact:
    if sha256(raw).hexdigest() != SUCCESSOR_ARTIFACT_SHA256:
        raise ValueError("Deep Strike successor artifact bytes drifted.")
    try:
        artifact = msgspec.json.decode(raw, type=DeepStrikeSuccessorArtifact)
    except msgspec.DecodeError as exc:
        raise ValueError("Deep Strike successor artifact schema is invalid.") from exc
    expected_counts = {
        "chaos-daemons-bridge-catalog": 17,
        "core-v2:court-of-slaughter-anvanth:2026-08": 6,
        "core-v2:chaos-daemons-roster:2026-07": 5,
    }
    observed = [(row.catalog_id, row.datasheet_id) for row in artifact.occurrences]
    if (
        artifact.schema != "core-v2-deep-strike-catalog-successor-v1"
        or artifact.ability_id != ABILITY_ID
        or artifact.source_id != SOURCE_ID
        or artifact.dependency_source_id != DEPENDENCY_ID
        or len(observed) != len(set(observed))
        or {catalog for catalog, _ in observed} != expected_counts.keys()
        or any(
            sum(catalog == owner for catalog, _ in observed) != count
            for owner, count in expected_counts.items()
        )
        or sha256(artifact.historical_text.encode()).hexdigest()
        != "51b2cb455ebc05e08e88ce55cf9d541a642a41d9fd5c51200f78270ec366a44e"
        or sha256(artifact.current_text.encode()).hexdigest()
        != "f30dacd179b74497c320f86d6ae5e0065a19bd6d8cc47b8317fc896c2fd59a4e"
    ):
        raise ValueError("Deep Strike successor identity or closure drifted.")
    return artifact


_SUCCESSOR: Final = successor_from_json_bytes(
    package_artifact_bytes(_SOURCE_PACKAGE, "artifacts/catalog-successor.json")
)
HISTORICAL_TEXT: Final = _SUCCESSOR.historical_text
CURRENT_TEXT: Final = _SUCCESSOR.current_text
DESCRIPTOR_HASHES: Final = {
    catalog: {
        row.datasheet_id: (row.historical_descriptor_sha256, row.current_descriptor_sha256)
        for row in _SUCCESSOR.occurrences
        if row.catalog_id == catalog
    }
    for catalog in dict.fromkeys(row.catalog_id for row in _SUCCESSOR.occurrences)
}


def descriptor_hash(ability: DatasheetAbilityDescriptor) -> str:
    return sha256(
        json.dumps(ability.to_payload(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def before_deep_strike_catalog(catalog: ArmyCatalog) -> ArmyCatalog:
    """Authenticate both exact descriptors; undo only reviewed prose and provenance."""
    if catalog.catalog_id not in DESCRIPTOR_HASHES:
        raise ValueError("Deep Strike successor catalog owner is unreviewed.")
    expected = DESCRIPTOR_HASHES[catalog.catalog_id]
    occurrences = tuple(
        (row.datasheet_id, ability)
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == ABILITY_ID
    )
    if len(occurrences) != len(expected) or {owner for owner, _ in occurrences} != set(expected):
        raise ValueError("Deep Strike successor occurrence closure drifted.")
    if not {SOURCE_ID, DEPENDENCY_ID}.issubset(catalog.source_ids):
        raise ValueError("Deep Strike successor source provenance is missing.")
    for owner, ability in occurrences:
        prior = replace(ability, effect_description=HISTORICAL_TEXT)
        if (
            descriptor_hash(ability) != expected[owner][1]
            or descriptor_hash(prior) != expected[owner][0]
        ):
            raise ValueError("Deep Strike successor descriptor drifted.")
    return replace(
        catalog,
        source_ids=tuple(s for s in catalog.source_ids if s not in {SOURCE_ID, DEPENDENCY_ID}),
        datasheets=tuple(
            replace(
                row,
                abilities=tuple(
                    replace(a, effect_description=HISTORICAL_TEXT)
                    if a.ability_id == ABILITY_ID
                    else a
                    for a in row.abilities
                ),
            )
            for row in catalog.datasheets
        ),
    )
