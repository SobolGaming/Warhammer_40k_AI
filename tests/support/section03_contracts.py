"""Constructed Core inputs at production seams; these are NOT authentic datasheets."""

from dataclasses import replace

from tests.support.section02_fixtures import MAULERFIEND, Section02Definitions
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.model_geometry import (
    BaseFootprintKind,
    FootprintPart,
    GeometrySourceKind,
    HeightSourceKind,
    ModelGeometry,
)


def oversized_contract(
    definitions: Section02Definitions, *, aircraft: bool = False
) -> UnitInstance:
    native = definitions.unit(MAULERFIEND, identity="constructed-oversized-contract")
    shape = ModelGeometry(
        BaseFootprintKind.CIRCULAR,
        (FootprintPart("contract-base", BaseFootprintKind.CIRCULAR, 4, 4),),
        3,
        GeometrySourceKind.MANUAL_OVERRIDE,
        "constructed:section03:8-inch-base",
        HeightSourceKind.MANUAL_OVERRIDE,
        "constructed:section03:3-inch-height",
    )
    unit = replace(
        native,
        name="CONSTRUCTED Core oversized contract",
        own_models=(replace(native.own_models[0], geometry=shape),),
    )
    return with_unit_keywords(unit, keywords=(*unit.keywords, "AIRCRAFT")) if aircraft else unit
