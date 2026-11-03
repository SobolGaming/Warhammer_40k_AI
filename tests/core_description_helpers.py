"""Authenticated projection for current description deltas and historical controls."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any, cast

from tools.core_deadly_demise_catalog_overlay import (
    CORE_DESCRIPTION_ARTIFACTS,
    CORE_DESCRIPTION_SOURCE_IDS,
)

from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash


@cache
def core_description_audit() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            Path(
                "data/source_audits/core_descriptions_2026_11/catalog-description-delta.json"
            ).read_bytes()
        ),
    )


def before_core_description_correction(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Authenticate complete current payload while projecting only the approved delta."""
    audit = core_description_audit()
    surface = next(
        row for row in audit["surfaces"] if row["catalog_id"] == package.army_catalog.catalog_id
    )
    if surface["surface"] == "daemons5":
        assert package.package_hash() == surface["package_hash"]
        return package
    occurrences = {(row["datasheet_id"], row["ability_id"]): row for row in surface["occurrences"]}
    wording = {row["ability_id"]: row["proposed_description"] for row in audit["wording"]}
    observed = [
        (row.datasheet_id, ability)
        for row in package.army_catalog.datasheets
        for ability in row.abilities
        if ability.ability_id in wording
    ]
    assert len(observed) == len(occurrences)
    for owner, ability in observed:
        assert ability.effect_description == wording[ability.ability_id]
        expected = {
            **occurrences[(owner, ability.ability_id)]["descriptor"],
            "effect_description": ability.effect_description,
        }
        assert ability.to_payload() == expected
    added_ids = {CORE_DESCRIPTION_SOURCE_IDS[ability.ability_id] for _, ability in observed}
    if "000008344" in {ability.ability_id for _, ability in observed}:
        added_ids.add("gw-11e-core-abilities:core:scout-move")
    assert package.army_catalog.source_ids == tuple(
        sorted(set(surface["catalog_source_ids"]) | added_ids)
    )
    prior_artifacts = tuple(SourceArtifactHash(**row) for row in surface["source_artifacts"])
    prefix = tuple(
        row for row in prior_artifacts if row.artifact_name != "core-stealth-2026-09.json"
    )
    assert package.source_artifacts == tuple(
        sorted((*prefix, *CORE_DESCRIPTION_ARTIFACTS), key=lambda artifact: artifact.artifact_name)
    )
    projected = replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            source_ids=tuple(surface["catalog_source_ids"]),
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(
                            ability,
                            effect_description=occurrences[(row.datasheet_id, ability.ability_id)][
                                "descriptor"
                            ]["effect_description"],
                        )
                        if (row.datasheet_id, ability.ability_id) in occurrences
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in package.army_catalog.datasheets
            ),
        ),
        source_artifacts=prior_artifacts,
    )
    assert projected.package_hash() == surface["package_hash"]
    return projected
