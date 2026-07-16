from __future__ import annotations

from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def charge_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_model_poses: tuple[Pose, ...],
    game_id: str,
    alpha_origins: dict[str, Pose] | None = None,
    enemy_unit_ids: tuple[str, ...] = ("enemy",),
    enemy_origins: dict[str, Pose] | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = charge_config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
    )
    armies = mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15a-battlefield",
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    origins = {} if alpha_origins is None else alpha_origins
    resolved_enemy_origins = {} if enemy_origins is None else enemy_origins
    battlefield = scenario.battlefield_state
    alpha_index = 0
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if army_id == "army-alpha":
            origin = origins.get(key, Pose.at(10.0, 20.0 + (alpha_index * 15.0)))
            poses = compact_test_unit_poses(origin=origin, model_count=len(unit.own_models))
            alpha_index += 1
        else:
            enemy_origin = resolved_enemy_origins.get(key)
            poses = (
                enemy_model_poses
                if enemy_origin is None
                else compact_test_unit_poses(
                    origin=enemy_origin,
                    model_count=len(unit.own_models),
                )
            )
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.battle_round = 1
    state.active_player_id = "player-a"
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def charge_config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15a-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
            ),
            army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup(),
    )


def mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        primary_mission_id="take-and-hold",
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


def army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
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
        unit_selections=tuple(unit_selection(unit_id) for unit_id in unit_selection_ids),
    )


def unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )
