"""Build the mixed Monster Mash / Cavalcade catalog from the versioned source review."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from tools.core_deadly_demise_catalog_overlay import (
    ABILITY_ID as DEADLY_DEMISE_ID,
)
from tools.core_deadly_demise_catalog_overlay import SOURCE_ARTIFACT as DEADLY_DEMISE_ARTIFACT
from tools.core_deep_strike_catalog_overlay import SOURCE_ARTIFACTS as DEEP_STRIKE_ARTIFACTS
from tools.generate_ability_support_matrix import BLOODLETTERS_HEIGHT_OVERRIDES
from tools.generate_cavalcade_v995_catalog import build_reviewed_datasheets
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
)
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.mfm_source import source_label_slug
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11 as cavalcade,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_monster_mash_2026_11 as monster_mash,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as july_roster,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_abilities_2026_09,
    core_deep_strike_description_2026_11,
    event_companion_base_size_rows,
    faction_detachments_2026_27,
    faction_subrules_2026_27,
    july_faction_packs_2026_07,
    mfm_2026_10,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    CHAOS_DAEMONS_KAIROS_FATEWEAVER_HEIGHT_OVERRIDES,
    ModelHeightOverride,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "chaos_daemons_monster_mash_2026_11/artifacts"
)
VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-monster-mash-v995", source_date=date(2026, 11, 22)
)
PACKAGE = DataPackageId(
    namespace="core-v2", package_name="chaos-daemons-monster-mash", version="2026-11-v995"
)
REVIEWED = DataPackageId(
    namespace="core-v2", package_name="monster-mash-reviewed-datasheets", version="2026-11-v995"
)
NEW_DATASHEET_IDS = (
    "000001105",
    "000001114",
    "000001117",
    "000001125",
    "000001465",
    "000001648",
)
INC_REQUIRED_DATASHEET_IDS = tuple(
    sorted((*NEW_DATASHEET_IDS, "000001132", "000001145", "000001148"))
)
DEEP_STRIKE_ID = "000008343"
KAIROS_REVIEWED_ABILITY_ID = "000001117:one-head-looks-back-aura"


def build_catalog_package() -> CanonicalCatalogPackage:
    base = cavalcade.catalog_package()
    review = json.loads((ARTIFACTS / "source-review.json").read_bytes())
    official_pdf = ROOT / review["official_pdf"]
    if (
        review["official_pdf_sha256"] != july_roster.OFFICIAL_PDF_SHA256
        or hashlib.sha256(official_pdf.read_bytes()).hexdigest() != july_roster.OFFICIAL_PDF_SHA256
        or review["points_source_package_id"] != mfm_2026_10.SOURCE_PACKAGE_ID
    ):
        raise ValueError("Monster Mash source pin drifted.")
    _check_base_evidence(review)
    reviewed_package = build_reviewed_datasheets(
        review=review,
        datasheet_ids=NEW_DATASHEET_IDS,
        reviewed_package=REVIEWED,
        output_package=PACKAGE,
        output_version=VERSION,
        heights=_reviewed_heights(),
    )
    added = _current_ability_descriptions(reviewed_package)
    detachment, enhancements, stratagems = _incursion_definitions()
    catalog = base.army_catalog
    mixed_catalog = replace(
        catalog,
        catalog_id=monster_mash.CATALOG_ID,
        source_package_id=PACKAGE.stable_identity(),
        datasheets=tuple(
            sorted(
                (*catalog.datasheets, *added.army_catalog.datasheets),
                key=lambda row: row.datasheet_id,
            )
        ),
        wargear=tuple(
            sorted((*catalog.wargear, *added.army_catalog.wargear), key=lambda row: row.wargear_id)
        ),
        detachments=(*catalog.detachments, detachment),
        enhancements=(*catalog.enhancements, *enhancements),
        stratagems=(*catalog.stratagems, *stratagems),
        source_ids=tuple(
            sorted(
                {
                    *catalog.source_ids,
                    *added.army_catalog.source_ids,
                    *detachment.source_ids,
                }
            )
        ),
    )
    added_sources = tuple(
        SourceArtifactHash(f"monster-mash-{row.artifact_name}", row.artifact_hash)
        for row in added.source_artifacts
    )
    evidence = tuple(
        SourceArtifactHash(
            f"monster-mash-{name}", hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()
        )
        for name in ("source-review.json", "geometry.json")
    )
    diagnostics = (*base.diagnostics, *added.diagnostics)
    if any(row.blocking for row in diagnostics):
        raise ValueError("Monster Mash source or geometry remains blocked.")
    return CanonicalCatalogPackage(
        package_id=PACKAGE,
        catalog_version=VERSION,
        source_edition=base.source_edition,
        source_artifacts=tuple(
            sorted(
                (
                    *base.source_artifacts,
                    *added_sources,
                    *evidence,
                    SourceArtifactHash("cavalcade-v995-catalog.json", cavalcade.CATALOG_SHA256),
                ),
                key=lambda row: row.artifact_name,
            )
        ),
        army_catalog=mixed_catalog,
        model_geometries=tuple(
            sorted(
                (*base.model_geometries, *added.model_geometries),
                key=lambda row: row.model_profile_id,
            )
        ),
        diagnostics=diagnostics,
    )


def _check_base_evidence(review: dict[str, object]) -> None:
    reviewed = review["datasheets"]
    if not isinstance(reviewed, list):
        raise TypeError("Monster Mash source review requires a datasheet list.")
    rows = event_companion_base_size_rows.BASE_SIZE_SOURCE_ROWS
    source_bases = {
        unit_name: dimensions
        for _, page, faction, section, unit_name, dimensions in rows
        if (page, faction, section) == (65, "Chaos Daemons", None)
    }
    for row in reviewed:
        if source_bases[row["name"]] != row["base_dimensions"]:
            raise ValueError(f"Monster Mash reviewed base drifted for {row['name']}.")


def _reviewed_heights() -> tuple[ModelHeightOverride, ...]:
    path = ARTIFACTS / "geometry.json"
    geometry = json.loads(path.read_bytes())
    return (
        *BLOODLETTERS_HEIGHT_OVERRIDES,
        *CHAOS_DAEMONS_KAIROS_FATEWEAVER_HEIGHT_OVERRIDES,
        *(
            ModelHeightOverride(
                datasheet_id=row["datasheet_id"],
                model_name=row["model_name"],
                height=row["height_mm"],
                height_units=GeometrySourceUnits.MILLIMETERS,
                height_source_id=f"monster-mash-v995:geometry:{row['datasheet_id']}:{index}",
                height_document_reference=path.relative_to(ROOT).as_posix(),
                reviewer_status=GeometryReviewStatus(row["reviewer_status"]),
                evidence_kind=GeometryEvidenceKind(row["evidence_kind"]),
            )
            for index, row in enumerate(geometry["heights"], 1)
        ),
    )


def _current_ability_descriptions(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    core_sources = {
        DEEP_STRIKE_ID: core_deep_strike_description_2026_11.source_rules()[0],
        DEADLY_DEMISE_ID: core_abilities_2026_09.source_rule_record(),
    }
    july = july_faction_packs_2026_07.chaos_daemons_runtime_updates()
    (kairos,) = (
        row
        for row in july.rows
        if row.row_id == "chaos-daemons:kairos-fateweaver:one-head-looks-back"
    )
    catalog = package.army_catalog
    observed = {
        (row.datasheet_id, ability.ability_id, ability.parameter_tokens)
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.source_kind is CatalogAbilitySourceKind.CORE
    }
    if observed != {
        *((owner, DEEP_STRIKE_ID, ()) for owner in NEW_DATASHEET_IDS),
        *(
            (owner, DEADLY_DEMISE_ID, ("D6",))
            for owner in ("000001105", "000001117", "000001465", "000001648")
        ),
        ("000001465", "000008338", ("6+",)),
    }:
        raise ValueError(f"Monster Mash reviewed Core ability closure drifted: {observed}.")
    (predecessor,) = (
        ability
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == KAIROS_REVIEWED_ABILITY_ID
    )
    # Runtime already supplies the July RuleIR under the stable predecessor ID.
    updated = replace(
        predecessor,
        name=kairos.rule_name,
        source_id=kairos.source_row_id,
        effect_description=kairos.normalized_rule_text,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        rule_ir_payload=None,
        rule_ir_diagnostics=(),
    )
    return replace(
        package,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        updated
                        if ability.ability_id == KAIROS_REVIEWED_ABILITY_ID
                        else replace(
                            ability, effect_description=core_sources[ability.ability_id].source_text
                        )
                        if ability.ability_id in core_sources
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in catalog.datasheets
            ),
            source_ids=tuple(
                sorted(
                    {
                        *catalog.source_ids,
                        *(source.source_id for source in core_sources.values()),
                        kairos.source_row_id,
                    }
                )
            ),
        ),
        source_artifacts=(
            *package.source_artifacts,
            *DEEP_STRIKE_ARTIFACTS,
            DEADLY_DEMISE_ARTIFACT,
        ),
    )


def _incursion_definitions() -> tuple[
    DetachmentDefinition, tuple[EnhancementDefinition, ...], tuple[StratagemDefinition, ...]
]:
    faction_id = "chaos-daemons"
    detachment_id = "daemonic-incursion"
    (row,) = (
        row
        for row in faction_detachments_2026_27.detachment_rows()
        if (row.faction_id, row.detachment_id) == (faction_id, detachment_id)
    )
    (mfm,) = (
        row
        for row in mfm_2026_10.faction_record(faction_id).detachments
        if row.detachment_id == detachment_id
    )
    if (mfm.detachment_point_cost, mfm.allowed_force_disposition_ids) != (
        3,
        ("take-and-hold", "disruption"),
    ):
        raise ValueError("Monster Mash October Daemonic Incursion admission drifted.")
    prices = {enhancement.enhancement_id: enhancement for enhancement in mfm.enhancements}
    enhancements = tuple(
        EnhancementDefinition(
            enhancement_id=source.enhancement_id,
            name=source.name,
            points=price.points,
            source_id=price.source_id,
        )
        for source in faction_subrules_2026_27.enhancement_rows()
        if (source.faction_id, source.detachment_id) == (faction_id, detachment_id)
        for price in (prices[source_label_slug(source.name)],)
    )
    stratagems = tuple(
        StratagemDefinition(
            stratagem_id=source.stratagem_id,
            name=source.name,
            source_id=source.source_id,
            command_point_cost=source.command_point_cost,
            timing_tags=(source.timing_descriptor,),
        )
        for source in faction_subrules_2026_27.stratagem_rows()
        if (source.faction_id, source.detachment_id) == (faction_id, detachment_id)
    )
    return (
        DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=row.faction_id,
            unit_datasheet_ids=INC_REQUIRED_DATASHEET_IDS,
            detachment_point_cost=mfm.detachment_point_cost,
            force_disposition_ids=mfm.allowed_force_disposition_ids,
            rule_source_ids=row.source_ids,
            source_ids=(*row.source_ids, mfm.source_id),
            enhancement_ids=tuple(definition.enhancement_id for definition in enhancements),
            stratagem_ids=tuple(definition.stratagem_id for definition in stratagems),
        ),
        enhancements,
        stratagems,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    check = parser.parse_args().check
    generated = build_catalog_package().to_json_bytes()
    path = ARTIFACTS / "catalog.json"
    if check:
        if path.read_bytes() != generated:
            raise SystemExit("Monster Mash v995 catalog is stale.")
        monster_mash.catalog_package()
    else:
        path.write_bytes(generated)


if __name__ == "__main__":
    main()
