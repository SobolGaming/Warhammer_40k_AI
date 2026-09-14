from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.game_state import (
    GameConfig,
)
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    PlayerPrimaryMissionAssignment,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def _config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    enemy_attached_unit_ids: tuple[str, str] | None = None,
    catalog: ArmyCatalog | None = None,
    alpha_datasheet_ids_by_selection_id: dict[str, str] | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15a-test"
        ),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
                datasheet_ids_by_selection_id=alpha_datasheet_ids_by_selection_id,
            ),
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
                character_unit_selection_ids=(
                    () if enemy_attached_unit_ids is None else (enemy_attached_unit_ids[1],)
                ),
                attachment_declarations=(
                    ()
                    if enemy_attached_unit_ids is None
                    else (
                        AttachmentDeclaration(
                            source_unit_selection_id=enemy_attached_unit_ids[1],
                            bodyguard_unit_selection_id=enemy_attached_unit_ids[0],
                        ),
                    )
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-3",
        primary_mission_assignments=(
            PlayerPrimaryMissionAssignment(
                player_id="player-a",
                force_disposition_id="purge-the-foe",
                primary_mission_id="primary-meatgrinder",
            ),
            PlayerPrimaryMissionAssignment(
                player_id="player-b",
                force_disposition_id="purge-the-foe",
                primary_mission_id="primary-meatgrinder",
            ),
        ),
        battlefield_layout_id=None,
        deployment_map_id="phase15a-open-map",
        terrain_layout_id="phase15a-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase15a-remote-objective",
                name="Phase 15A Remote Objective",
                objective_role=ObjectiveMarkerRole.CENTRAL,
                x_inches=95.0,
                y_inches=95.0,
                source_id="phase15a-test",
            ),
        ),
        deployment_zones=(),
        battlefield_regions=(),
        terrain_areas=(),
        terrain_features=(),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    character_unit_selection_ids: tuple[str, ...] = (),
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    datasheet_ids_by_selection_id: dict[str, str] | None = None,
) -> ArmyMusterRequest:
    thousand_sons_roster = datasheet_ids_by_selection_id is not None and any(
        datasheet_id in {"000001029", "phase15a-thousand-sons-psyker-anchor"}
        for datasheet_id in datasheet_ids_by_selection_id.values()
    )
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="TS" if thousand_sons_roster else "core-marine-force",
            detachment_ids=(
                "phase15a-thousand-sons-detachment"
                if thousand_sons_roster
                else "core-combined-arms",
            ),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            _unit_selection(
                unit_id,
                catalog=catalog,
                is_character=unit_id in character_unit_selection_ids,
                datasheet_id=(
                    None
                    if datasheet_ids_by_selection_id is None
                    else datasheet_ids_by_selection_id.get(unit_id)
                ),
            )
            for unit_id in unit_selection_ids
        ),
        attachment_declarations=attachment_declarations,
    )


def _unit_selection(
    unit_selection_id: str,
    *,
    catalog: ArmyCatalog,
    is_character: bool = False,
    datasheet_id: str | None = None,
) -> UnitMusterSelection:
    if datasheet_id is not None and is_character:
        raise AssertionError("A character fixture cannot also override its datasheet ID.")
    resolved_datasheet_id = (
        datasheet_id
        if datasheet_id is not None
        else "core-character-leader"
        if is_character
        else "core-intercessor-like-infantry"
    )
    model_profile_selections: tuple[ModelProfileSelection, ...]
    if datasheet_id is None:
        model_profile_selections = (
            ModelProfileSelection(
                model_profile_id=(
                    "core-character-leader" if is_character else "core-intercessor-like"
                ),
                model_count=1 if is_character else 5,
            ),
        )
    else:
        datasheet = catalog.datasheet_by_id(resolved_datasheet_id)
        model_profile_selections = tuple(
            ModelProfileSelection(
                model_profile_id=composition.model_profile_id,
                model_count=composition.min_models,
            )
            for composition in datasheet.composition
        )
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=resolved_datasheet_id,
        model_profile_selections=model_profile_selections,
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


__all__ = (
    "_army_muster_request",
    "_config",
    "_mission_setup",
    "_mustered_armies",
    "_unit_selection",
)
