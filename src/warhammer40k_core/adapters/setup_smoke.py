from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup, instantiate_terrain_layout_template
from warhammer40k_core.engine.reserves import ReserveUnitPointValue
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

_SMOKE_IMPLEMENTED_MISSION_POOL_ENTRY_ID = "mission-take-and-hold-vs-purge-the-foe-layout-3"
_SMOKE_IMPLEMENTED_TERRAIN_LAYOUT_ID = "take-and-hold-vs-purge-the-foe-layout-3"
_SMOKE_TYPED_BATTLEFIELD_LAYOUT_ID = "take-and-hold-vs-take-and-hold-layout-3"


def canonical_setup_prebattle_smoke_config(
    *,
    game_id: str = "setup-prebattle-ui-smoke",
) -> GameConfig:
    """Config that emits setup/pre-battle adapter request families from real engine state."""
    catalog = _setup_prebattle_smoke_catalog()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-setup-prebattle-ui-smoke"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    _unit_selection(unit_selection_id="scout-redeploy-unit"),
                    _unit_selection(
                        unit_selection_id="strategic-reserve-unit",
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    ),
                    _unit_selection(
                        unit_selection_id="deep-strike-unit",
                        datasheet_id="core-deep-strike-unit",
                        model_profile_id="core-deep-strike-model",
                        model_count=3,
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(_unit_selection(unit_selection_id="scout-redeploy-unit"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_setup_prebattle_smoke_mission_setup(),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:strategic-reserve-unit",
                points=300,
                source_id="setup-smoke-points:army-alpha:strategic-reserve-unit",
            ),
        ),
    )


def _setup_prebattle_smoke_mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    implemented_setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=_SMOKE_IMPLEMENTED_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=_SMOKE_IMPLEMENTED_TERRAIN_LAYOUT_ID,
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    typed_layout = mission_pack.battlefield_layout(_SMOKE_TYPED_BATTLEFIELD_LAYOUT_ID)
    typed_deployment_map = mission_pack.deployment_map(typed_layout.deployment_map_id)
    typed_terrain_layout = mission_pack.terrain_layout_template(typed_layout.terrain_layout_id)
    return replace(
        implemented_setup,
        battlefield_layout_id=typed_layout.battlefield_layout_id,
        deployment_map_id=typed_layout.deployment_map_id,
        terrain_layout_id=typed_layout.terrain_layout_id,
        battlefield_width_inches=typed_layout.battlefield_width_inches,
        battlefield_depth_inches=typed_layout.battlefield_depth_inches,
        objective_markers=typed_layout.objective_markers,
        deployment_zones=typed_deployment_map.deployment_zones_for_players(
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
        battlefield_regions=typed_layout.battlefield_regions,
        terrain_areas=typed_layout.terrain_areas,
        terrain_features=instantiate_terrain_layout_template(typed_terrain_layout),
        objective_terrain_areas=typed_layout.objective_terrain_areas,
    )


def _setup_prebattle_smoke_catalog() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheets = tuple(
        _setup_smoke_datasheet(datasheet)
        if datasheet.datasheet_id == "core-intercessor-like-infantry"
        else datasheet
        for datasheet in catalog.datasheets
    )
    return replace(catalog, datasheets=datasheets)


def _setup_smoke_datasheet(datasheet: DatasheetDefinition) -> DatasheetDefinition:
    keywords = _with_keywords(datasheet.keywords.keywords, ("REDEPLOY", "SCOUTS"))
    scouts_descriptors = _scouts_ability_descriptors(datasheet_id=datasheet.datasheet_id)
    retained_abilities = tuple(
        ability
        for ability in datasheet.abilities
        if "scouts" not in {tag.lower() for tag in ability.timing_tags}
    )
    return replace(
        datasheet,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=datasheet.keywords.faction_keywords,
        ),
        abilities=(*retained_abilities, *scouts_descriptors),
    )


def _with_keywords(existing: tuple[str, ...], added: tuple[str, ...]) -> tuple[str, ...]:
    values = [*existing]
    normalized = {value.upper().replace(" ", "_") for value in values}
    for keyword in added:
        if keyword.upper().replace(" ", "_") not in normalized:
            values.append(keyword)
            normalized.add(keyword.upper().replace(" ", "_"))
    return tuple(values)


def _scouts_ability_descriptors(*, datasheet_id: str) -> tuple[DatasheetAbilityDescriptor, ...]:
    return (
        DatasheetAbilityDescriptor(
            ability_id="core-scouts",
            name="CORE Scouts 6",
            source_id=f"datasheet:{datasheet_id}:ability:setup-smoke-scouts-6",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            effect_description="CORE Scouts 6 descriptor.",
            timing_tags=("before_battle", "scouts"),
            parameter_tokens=("6",),
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=unit_selections,
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )
