"""Small immutable catalogs; each request and runtime army is independently owned.

Core overlays below are analytical supported inputs, not faction-provider admission.
Real datasheet kernels use an unmodified selected catalog in test_native.py.
"""

import json
from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import EnhancementDefinition, EnhancementSubtype
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    WarlordSelection,
)
from warhammer40k_core.engine.list_validation import (
    BattleSize,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.roster_points import RosterUnitPointValue
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

BODY = "core-intercessor-like-infantry"
LEADER = "core-character-leader"
SUPPORT = "core-character-support"
UPGRADE = "s25-upgrade"
ORDINARY = tuple(f"s25-enhancement-{i}" for i in range(5))
NATIVE_IDS = ("000004078", "000004080", "000000593", "000000599", "000004193")


@pytest.fixture(scope="session")
def section25_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    before = sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    elapsed = perf_counter() - start
    print(f"Section25 preparation: {elapsed:.6f}s; five immutable real datasheet definitions")
    yield Section02Definitions(package, elapsed)
    assert sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest() == before


@pytest.fixture(scope="session")
def section25_catalog() -> Iterator[ArmyCatalog]:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    enhancements = (
        *(
            EnhancementDefinition(e, e, f"constructed:s25:{e}", points=10 + i)
            for i, e in enumerate(ORDINARY)
        ),
        EnhancementDefinition(
            UPGRADE,
            UPGRADE,
            "constructed:s25:upgrade",
            points=20,
            subtypes=(EnhancementSubtype.UPGRADE,),
        ),
    )
    catalog = replace(
        base,
        enhancements=enhancements,
        detachments=(
            replace(
                base.detachments[0], enhancement_ids=(*ORDINARY, UPGRADE), detachment_point_cost=1
            ),
        ),
    )
    before = sha256(json.dumps(catalog.to_payload(), sort_keys=True).encode()).hexdigest()
    yield catalog
    assert sha256(json.dumps(catalog.to_payload(), sort_keys=True).encode()).hexdigest() == before


def selection(catalog: ArmyCatalog, identity: str, sheet: str = LEADER) -> UnitMusterSelection:
    datasheet = catalog.datasheet_by_id(sheet)
    return UnitMusterSelection(
        unit_selection_id=identity,
        datasheet_id=sheet,
        model_profile_selections=tuple(
            ModelProfileSelection(p.model_profile_id, p.min_models) for p in datasheet.composition
        ),
    )


def request(
    catalog: ArmyCatalog,
    *,
    size: BattleSize = BattleSize.INCURSION,
    units: tuple[UnitMusterSelection, ...] | None = None,
    assignments: tuple[EnhancementAssignment, ...] = (),
) -> ArmyMusterRequest:
    units = units if units is not None else (selection(catalog, "commander"),)
    first = units[0]
    return ArmyMusterRequest(
        army_id="s25-army",
        player_id="owner",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            catalog.detachments[0].faction_id,
            (catalog.detachments[0].detachment_id,),
            tuple(dict.fromkeys(a.enhancement_id for a in assignments)),
        ),
        force_disposition_id=catalog.detachments[0].force_disposition_ids[0],
        unit_selections=units,
        unit_points=tuple(
            RosterUnitPointValue(u.unit_selection_id, 50, "constructed:s25:unit-points")
            for u in units
        ),
        enhancement_assignments=assignments,
        warlord_selection=WarlordSelection(
            unit_selection_id=first.unit_selection_id,
            source_id="constructed:s25:warlord",
            model_profile_id=first.model_profile_selections[0].model_profile_id,
            model_index=1,
        ),
        roster_legality_required=True,
        battle_size=size,
    )


def assignment(unit: UnitMusterSelection, enhancement: str = ORDINARY[0]) -> EnhancementAssignment:
    return EnhancementAssignment(
        enhancement_id=enhancement,
        target_unit_selection_id=unit.unit_selection_id,
        source_id="constructed:s25:assignment",
        model_profile_id=unit.model_profile_selections[0].model_profile_id,
        model_index=1,
    )
