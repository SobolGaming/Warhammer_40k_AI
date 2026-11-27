"""Borrow known fixture geometry to exercise the two bridged Fortification rows."""

from dataclasses import replace
from functools import cache
from typing import cast

from tests.support.section02_fixtures import Section02Definitions
from tests.support.wahapedia_source_fixtures import wahapedia_source_artifacts

from warhammer40k_core.core.datasheet import CatalogAbilitySupport, DatasheetAbilityDescriptor
from warhammer40k_core.engine.catalog_contextual_status_consumption import (
    CATALOG_IR_FORTIFICATION_DESPERATE_ESCAPE_CONSUMER_ID,
    CATALOG_IR_FORTIFICATION_TARGET_PERMISSION_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_ir_consumers_for_rule
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.wahapedia_datasheet_ability_bridge import bridge_datasheet_abilities

GNARLMAW = "000001470"
SKULL_ALTAR = "000001588"


@cache
def fortification_ability(datasheet_id: str) -> DatasheetAbilityDescriptor:
    # The September official pack confirms this shared bridged clause.
    (row,) = (
        row
        for row in bridge_datasheet_abilities(
            source_artifacts=wahapedia_source_artifacts(),
            datasheet_ids=(datasheet_id,),
        )
        if row.source_row_id == f"{datasheet_id}:5"
    )
    descriptor = row.descriptor
    assert descriptor.support is CatalogAbilitySupport.GENERIC_RULE_IR
    rule = RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload))
    assert set(catalog_rule_ir_consumers_for_rule(rule)) == {
        CATALOG_IR_FORTIFICATION_TARGET_PERMISSION_CONSUMER_ID,
        CATALOG_IR_FORTIFICATION_DESPERATE_ESCAPE_CONSUMER_ID,
    }
    return descriptor


def with_fortification(
    definitions: Section02Definitions,
    *,
    provider_sheet: str,
    fortification_sheet: str | None,
    additional_abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
) -> Section02Definitions:
    catalog = definitions.package.army_catalog
    fixture = catalog.datasheet_by_id(provider_sheet)
    abilities = additional_abilities
    if fortification_sheet is not None:
        abilities = (fortification_ability(fortification_sheet), *abilities)
    source_ids = {ability.source_id for ability in abilities}
    fixture = replace(
        fixture,
        keywords=replace(fixture.keywords, keywords=(*fixture.keywords.keywords, "FORTIFICATION")),
        abilities=(*fixture.abilities, *abilities),
        source_ids=tuple(sorted({*fixture.source_ids, *source_ids})),
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            fixture if row.datasheet_id == provider_sheet else row for row in catalog.datasheets
        ),
        source_ids=tuple(sorted({*catalog.source_ids, *source_ids})),
    )
    return replace(definitions, package=replace(definitions.package, army_catalog=catalog))
