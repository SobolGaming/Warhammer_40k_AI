"""Real canonical models and shared engine queries for Core 13.11.01 regressions."""

from __future__ import annotations

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _config,
    _configure_shooting_battle_state,
    _display_geometry,
    _first_weapon_profile,
    _mustered_armies,
    _scenario_with_unit_pose,
)
from warhammer40k_core.core.terrain_areas import TerrainAreaClassification
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting_eligibility import _hidden_target_model_ids
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.ranged_rule_effects import (
    unit_hidden_payload,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    shooting_target_candidate_for_model,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)

SHOOTER = "army-alpha:shooter"
TARGET = "army-beta:enemy"
ALTERNATE = "army-beta:alternate"


def scene(
    *,
    dense_occupancy: bool = False,
    hidden: bool = True,
    classification: TerrainAreaClassification = TerrainAreaClassification.DENSE,
    attached_target: bool = False,
    target_x: float = 24.3,
    wall_y: float = 35.0,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _config(
        game_id="order78-gone-to-ground",
        alpha_unit_ids=("shooter",),
        alpha_datasheets=None,
        alpha_unit_specs=(
            ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", 1),
        enemy_unit_specs=(
            ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 1),
            ("alternate", "core-intercessor-like-infantry", "core-intercessor-like", 1),
            *(
                ((("leader", "core-character-leader", "core-character-leader", 1),))
                if attached_target
                else ()
            ),
        ),
        enemy_attachment_declarations=(AttachmentDeclaration("leader", "enemy"),)
        if attached_target
        else (),
        catalog=_compact_intercessor_catalog(_canonical_catalog()),
    )
    dense_geometry = _display_geometry(
        center_x_inches=23.0,
        center_y_inches=wall_y,
        width_inches=4.0 if dense_occupancy else 0.2,
        depth_inches=0.6,
    )
    dense = TerrainFeatureDefinition(
        feature_id="order78-intervening-dense",
        feature_kind=TerrainFeatureKind.RUINS,
        classification=classification,
        footprint_center_x_inches=23.0,
        footprint_center_y_inches=wall_y,
        footprint_width_inches=4.0 if dense_occupancy else 0.2,
        footprint_depth_inches=0.6,
        rules_footprint_polygon=dense_geometry.footprint_polygon,
        display_geometry=dense_geometry,
        walls=(
            TerrainWallDefinition(
                wall_id="order78-partial-wall",
                center_x_inches=23.0,
                center_y_inches=wall_y,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=0.6,
                height_inches=4.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="order78-ground",
                center_x_inches=23.0,
                center_y_inches=wall_y,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=0.6,
                thickness_inches=0.1,
            ),
        ),
        source_id="order78-probe",
    )
    assert config.mission_setup is not None
    config = replace(config, mission_setup=replace(config.mission_setup, terrain_features=(dense,)))
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order78-battlefield",
        armies=armies,
        battlefield_width_inches=100.0,
        battlefield_depth_inches=60.0,
    )
    positions = {
        "shooter": (10.0, 35.0),
        "enemy": (target_x, 35.0),
        "alternate": (24.3, 41.0),
        "leader": (target_x + 1.6, 35.0),
    }
    for army in armies:
        for unit in army.units:
            x, y = positions[unit.unit_instance_id.split(":", 1)[1]]
            scenario = _scenario_with_unit_pose(
                scenario=scenario,
                unit=unit,
                army_id=army.army_id,
                player_id=army.player_id,
                poses=(Pose.at(x, y),),
            )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.decision_controller.event_log = EventLog()
    assert lifecycle.state is not None
    _configure_shooting_battle_state(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        armies=armies,
        battlefield=replace(scenario.battlefield_state, terrain_features=(dense,)),
        units=units,
        embarked_unit_ids=(),
    )
    assert lifecycle.state is not None
    if hidden:
        lifecycle.state.record_persisting_effect(
            PersistingEffect(
                effect_id="order78:hidden",
                source_rule_id="order78:fixture-hidden",
                owner_player_id="player-b",
                target_unit_instance_ids=(
                    rules_unit_view_by_id(
                        state=lifecycle.state, unit_instance_id=TARGET
                    ).unit_instance_id,
                ),
                started_battle_round=1,
                started_phase=BattlePhase.SHOOTING,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=unit_hidden_payload(source_rule_kind="core-audit-fixture"),
            )
        )
    return lifecycle, units


def candidate_for_scene(
    lifecycle: GameLifecycle,
    units: dict[str, UnitInstance],
    *,
    detection_bonus: int = 0,
) -> ShootingTargetCandidate:
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    ruleset = lifecycle.config.ruleset_descriptor
    target = rules_unit_view_by_id(state=state, unit_instance_id=TARGET)
    recent = state.unit_made_ranged_attacks_current_or_previous_turn(
        unit_instance_id=target.unit_instance_id
    )
    return shooting_target_candidate_for_model(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=ruleset,
        attacker_unit=units["shooter"],
        attacker_model_instance_id=units["shooter"].own_models[0].model_instance_id,
        weapon_profile=_first_weapon_profile(lifecycle, units["shooter"]),
        target_unit_id=TARGET,
        terrain_features=state.mission_setup.terrain_features,
        terrain_areas=state.mission_setup.terrain_areas,
        hidden_target_model_ids=_hidden_target_model_ids(
            state=state, ruleset_descriptor=ruleset, target_unit_ids=(target.unit_instance_id,)
        ),
        target_unit_ids_with_recent_ranged_attacks=(target.unit_instance_id,) if recent else (),
        target_detection_range_bonus_inches=detection_bonus,
    )


def shared_los(lifecycle: GameLifecycle, units: dict[str, UnitInstance]) -> bool:
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    return unit_has_line_of_sight_to_target(
        state=state,
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        observing_unit=units["shooter"],
        target_unit_id=TARGET,
        terrain_features=state.mission_setup.terrain_features,
        terrain_areas=state.mission_setup.terrain_areas,
        placed_alive_models_only=True,
    )
