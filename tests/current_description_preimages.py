"""Scoped current adapter preimages; unrelated current fields are never projected away."""

from dataclasses import replace

from tools.core_deadly_demise_catalog_overlay import (
    CORE_DESCRIPTION_ARTIFACTS,
    CORE_DESCRIPTION_SOURCE_IDS,
)
from tools.core_deep_strike_catalog_overlay import SOURCE_ARTIFACTS

from tests.core_description_helpers import core_description_audit
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.core_deep_strike_successor import (
    DEPENDENCY_ID,
    SOURCE_ID,
    before_deep_strike_catalog,
)


def current_core_description_preimage(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Validate complete selected descriptors/owners; reverse only wording and additions."""
    audit = core_description_audit()
    surface = next(
        row for row in audit["surfaces"] if row["catalog_id"] == package.army_catalog.catalog_id
    )
    occurrences = {
        (r["datasheet_id"], r["ability_id"]): r["descriptor"] for r in surface["occurrences"]
    }
    wording = {r["ability_id"]: r["proposed_description"] for r in audit["wording"]}
    observed = [
        (row.datasheet_id, a)
        for row in package.army_catalog.datasheets
        for a in row.abilities
        if a.ability_id in wording
    ]
    if len(observed) != len(occurrences) or {(o, a.ability_id) for o, a in observed} != set(
        occurrences
    ):
        raise ValueError("Current Core description occurrence/owner closure changed.")
    for owner, ability in observed:
        if ability.to_payload() != {
            **occurrences[(owner, ability.ability_id)],
            "effect_description": wording[ability.ability_id],
        }:
            raise ValueError("Current Core description complete selected descriptor changed.")
    if surface["surface"] == "daemons5":
        # This surface preserves its four current Stealth descriptors without correction.
        return package
    added_ids = {CORE_DESCRIPTION_SOURCE_IDS[a.ability_id] for _, a in observed}
    if "000008344" in {a.ability_id for _, a in observed}:
        added_ids.add("gw-11e-core-abilities:core:scout-move")
    if not added_ids <= set(package.army_catalog.source_ids):
        raise ValueError("Current Core description source additions changed.")
    if not set(CORE_DESCRIPTION_ARTIFACTS) <= set(package.source_artifacts):
        raise ValueError("Current Core description artifact additions changed.")
    return replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            source_ids=tuple(s for s in package.army_catalog.source_ids if s not in added_ids),
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(
                            a,
                            effect_description=occurrences[(row.datasheet_id, a.ability_id)][
                                "effect_description"
                            ],
                        )
                        if (row.datasheet_id, a.ability_id) in occurrences
                        else a
                        for a in row.abilities
                    ),
                )
                for row in package.army_catalog.datasheets
            ),
        ),
        source_artifacts=tuple(
            a for a in package.source_artifacts if a not in CORE_DESCRIPTION_ARTIFACTS
        ),
    )


def current_deep_strike_preimage(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Use the live selected-descriptor boundary, preserving every unrelated input."""
    if not {SOURCE_ID, DEPENDENCY_ID} <= set(package.army_catalog.source_ids):
        raise ValueError("Current Deep Strike source additions changed.")
    if not set(SOURCE_ARTIFACTS) <= set(package.source_artifacts):
        raise ValueError("Current Deep Strike artifact additions changed.")
    catalog = before_deep_strike_catalog(package.army_catalog)
    return replace(
        package,
        army_catalog=replace(
            catalog,
            source_ids=tuple(s for s in catalog.source_ids if s not in {SOURCE_ID, DEPENDENCY_ID}),
        ),
        source_artifacts=tuple(a for a in package.source_artifacts if a not in SOURCE_ARTIFACTS),
    )
