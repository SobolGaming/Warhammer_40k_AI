"""Real facade fixture for obstacle-induced mandatory endpoint impossibility."""

from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import select_source, select_targets
from tests.charge_endpoint_helpers import select_attached_source
from tests.phase15a_charge_declaration_helpers import (
    charge_config,
    compact_test_unit_poses,
    mustered_armies,
    unit_placement_at,
)
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.geometry.base import BaseShape, CircularBase
from warhammer40k_core.geometry.movement_reachability import MovementGoal, MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model, ModelVolume

SOURCE = "army-alpha:source"
TARGET = "army-beta:enemy"


def wall_endpoint_query(*, base: BaseShape, goal_kind: str = "model") -> MovementReachabilityQuery:
    """Continuous endpoint lens blocked by a real feature wall, with all facings allowed."""
    source = Model("source", Pose.at(10, 20, facing_degrees=37), base, ModelVolume(1))
    target = Model(
        "target", Pose.at(10, 23.74 + base.max_radius() + 1.5), CircularBase(0.5), ModelVolume(1)
    )
    feature = mandatory_endpoint_wall(width=1.8, depth=1.8)
    feature = replace(
        feature,
        walls=(replace(feature.walls[0], width_inches=1.2, depth_inches=1.2, rotation_degrees=37),),
    )
    goal = MovementGoal(models=(target,), range_inches=1)
    if goal_kind == "engagement":
        goal = MovementGoal(models=(target,), horizontal_inches=1, vertical_inches=5)
    elif goal_kind == "disk":
        goal = MovementGoal(
            disk=(target.pose, CircularBase(0.5)), horizontal_inches=1, vertical_inches=5
        )
    elif goal_kind == "polygon":
        y = target.pose.position.y - 0.5
        goal = MovementGoal(
            polygons=(((9.99, y), (10.01, y), (10.01, y + 1), (9.99, y + 1)),),
            horizontal_inches=1,
            vertical_inches=5,
        )
    legality = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.CONSOLIDATE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )
    witness = PathWitness.for_paths(((source.model_id, (source.pose, source.pose)),))
    return MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=source,
            witness=witness,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            friendly_models=(),
            enemy_models=(target,),
            terrain=(),
            movement_distance_budget_inches=3.75,
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=source,
            witness=witness,
            terrain=feature.terrain_volumes(),
            terrain_features=(feature,),
        ),
        goal=goal,
    )


def mandatory_endpoint_wall(
    *, x: float = 10, width: float = 0.8, depth: float = 0.4
) -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=x,
        center_y_inches=24,
        width_inches=width,
        depth_inches=depth,
        display_template_id=None,
    )
    return TerrainFeatureDefinition(
        feature_id="mandatory-endpoint-wall",
        feature_kind=TerrainFeatureKind.INDUSTRIAL_STRUCTURES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=24,
        footprint_width_inches=width,
        footprint_depth_inches=depth,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=x,
                center_y_inches=24,
                bottom_z_inches=0,
                width_inches=width,
                depth_inches=depth,
                height_inches=5,
            ),
        ),
        classification=TerrainAreaClassification.DENSE,
    )


def blocked_charge_session(*, attached: bool = False) -> LocalGameSession:
    config = charge_config(
        game_id="order74-charge-preflight",
        alpha_unit_ids=("source", "leader") if attached else ("source",),
        alpha_attached_unit_ids=("source", "leader") if attached else None,
        enemy_unit_ids=("enemy",),
    )
    assert config.mission_setup is not None
    mission = replace(config.mission_setup, terrain_features=(mandatory_endpoint_wall(),))
    config = replace(
        config,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids
        ),
    )
    armies = mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="mandatory-endpoint-battlefield",
        armies=armies,
        battlefield_width_inches=100,
        battlefield_depth_inches=100,
    )
    battlefield = replace(scenario.battlefield_state, terrain_features=mission.terrain_features)
    for army in armies:
        for unit in army.units:
            poses = compact_test_unit_poses(
                origin=Pose.at(10, 21 if army.player_id == "player-a" else 26),
                model_count=len(unit.own_models),
            )
            if army.player_id == "player-a":
                if not attached:
                    poses = (Pose.at(10, 20), *poses[1:])
                elif unit.unit_instance_id == SOURCE:
                    poses = compact_test_unit_poses(
                        origin=Pose.at(11.4, 21.25), model_count=len(unit.own_models)
                    )
                else:
                    # The 40 mm Leader starts 4 mm behind the ordinary 32 mm
                    # model, preserving its 3.740157-inch preferred-distance bound.
                    poses = (Pose.at(10, 20 - 4 / 25.4),)
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=poses)
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
    decisions = GameLifecycle().decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(state, decisions=decisions, config=config)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    from tests.charge_distance_helpers import add_modifier

    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="audit-roll", kind="modify_dice_roll", delta=20)
    add_modifier(lifecycle.state, effect_id="audit-move", kind="modify_move_distance", delta=-8.25)
    return LocalGameSession(lifecycle)


def blocked_charge_request(session: LocalGameSession) -> DecisionRequest:
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions), unit_instance_id=SOURCE
    )
    request = (
        select_attached_source(session) if view.is_attached_rules_unit else select_source(session)
    )
    return select_targets(session, request, (TARGET,))


def blocked_charge_payload(session: LocalGameSession, request: DecisionRequest) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions), unit_instance_id=SOURCE
    )
    placement = charge_movement_placement(
        scenario=battlefield_scenario_for_state(state=state), unit_instance_id=view.unit_instance_id
    )
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(model.pose.position.x, model.pose.position.y + 1.5),
                    Pose.at(model.pose.position.x, model.pose.position.y + 3),
                ),
            )
            for model in placement.model_placements
        )
    )
    return cast(
        JsonValue,
        ChargeMoveProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.CHARGE_MOVE,
            unit_instance_id=view.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(TARGET,),
            witness=witness,
        ).to_payload(),
    )
