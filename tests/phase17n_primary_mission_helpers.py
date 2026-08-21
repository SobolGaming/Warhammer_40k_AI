from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import (
    battle_state,
    default_unit_selection,
    with_model_offsets,
)
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
)
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.mission_action_options import mission_action_for_state
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    apply_mission_decision,
    request_mission_action_opportunity,
    request_mission_action_start,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_deployment_zone,
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
    record_primary_turn_start_evidence_event,
)
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_choices import (
    apply_primary_mission_choice,
    consecrate_choice_request,
    locate_and_deny_setup_choice_request,
    punishment_choice_request,
    sensor_sweep_marker_removal_choice_request,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE,
    mark_pending_primary_scoring_boundaries,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    build_primary_rules_unit_turn_start_snapshot,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import PrimaryObjectiveTurnStartState
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def phase17n_event_setup(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    attacker_player_id: str = "player-a",
    defender_player_id: str = "player-b",
) -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id=f"mission-{layout_id}",
        terrain_layout_id=layout_id,
        attacker_player_id=attacker_player_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_player_id=defender_player_id,
        defender_force_disposition_id=defender_force_disposition_id,
    )


def phase17n_started_primary_action_fixture(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    player_id: str,
    mission_action_id: str,
    current_phase: BattlePhase,
    player_unit_count: int = 1,
    vanguard_enemy_position: str | None = None,
    target_objective_id: str | None = None,
) -> tuple[GameState, DecisionController, MissionActionState, str]:
    if player_unit_count == 1:
        state = battle_state()
    elif player_unit_count == 2 and player_id == "player-a":
        state = battle_state(
            player_a_units=(
                default_unit_selection("intercessor-unit-1"),
                default_unit_selection("intercessor-unit-2"),
            )
        )
    else:
        raise AssertionError("Phase 17N action fixture supports one unit or two player-a units.")
    state.mission_setup = phase17n_event_setup(
        layout_id=layout_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_force_disposition_id=defender_force_disposition_id,
    )
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=state.mission_setup.battlefield_depth_inches,
        terrain_features=state.mission_setup.terrain_features,
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.active_player_id = player_id
    runtime_action = mission_action_for_state(
        state=state,
        mission_action_id=mission_action_id,
    )
    state.battle_round = (
        2
        if runtime_action.start_timing == "shooting_phase_action_start_from_battle_round_two"
        else 1
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    units = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
    )
    assert len(units) == player_unit_count
    unit = units[0]
    assert state.mission_setup is not None
    if runtime_action.target_policy == "trappable_terrain_area":
        target_area = next(
            area
            for area in mission_logical_terrain_areas(state.mission_setup)
            if not logical_terrain_area_within_player_deployment_zone(
                area,
                mission_setup=state.mission_setup,
                player_id=player_id,
            )
        )
        target_id = target_area.logical_terrain_area_id
        target_point = target_area.members[0].footprint_polygon[0]
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            target_point.x_inches + (index * 0.1),
                            target_point.y_inches,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )
    elif runtime_action.target_policy == "terrain_area_in_enemy_territory":
        opponent_id = next(
            candidate_id for candidate_id in state.player_ids if candidate_id != player_id
        )
        target_area = next(
            area
            for area in mission_logical_terrain_areas(state.mission_setup)
            if logical_terrain_area_within_player_territory(
                area,
                mission_setup=state.mission_setup,
                player_id=opponent_id,
            )
        )
        target_id = target_area.logical_terrain_area_id
        min_x, min_y, max_x, max_y = target_area.bounds()
        target_x = (min_x + max_x) / 2.0
        target_y = (min_y + max_y) / 2.0
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            target_x + (index * 0.1),
                            target_y,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )
        if vanguard_enemy_position is not None:
            if vanguard_enemy_position not in {"inside", "near_outside"}:
                raise AssertionError("Unsupported Vanguard enemy fixture position.")
            enemy = next(
                candidate
                for army in state.army_definitions
                if army.player_id != player_id
                for candidate in army.units
            )
            enemy_placement = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
            enemy_y = min_y + 1.0 if vanguard_enemy_position == "inside" else min_y - 1.5
            enemy_x = min_x + 1.0 if vanguard_enemy_position == "inside" else target_x
            state.battlefield_state = state.battlefield_state.with_unit_placement(
                replace(
                    enemy_placement,
                    model_placements=tuple(
                        replace(
                            model_placement,
                            pose=Pose.at(
                                enemy_x + (index * 0.1),
                                enemy_y,
                                model_placement.pose.position.z,
                                facing_degrees=model_placement.pose.facing.degrees,
                            ),
                        )
                        for index, model_placement in enumerate(enemy_placement.model_placements)
                    ),
                )
            )
    elif runtime_action.target_policy == "visible_enemy_unit_within_18_not_surveilled_this_turn":
        target_unit = next(
            enemy
            for army in state.army_definitions
            if army.player_id != player_id
            for enemy in army.units
        )
        target_id = target_unit.unit_instance_id
        target_placement = state.battlefield_state.unit_placement_by_id(target_id)
        target_pose = target_placement.model_placements[0].pose
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            target_pose.position.x - 6.0 - (index * 0.1),
                            target_pose.position.y,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )
    else:
        if target_objective_id is None:
            target_marker = next(
                marker
                for marker in state.mission_setup.objective_markers
                if marker.objective_role is ObjectiveMarkerRole.CENTRAL
            )
        else:
            target_marker = next(
                marker
                for marker in state.mission_setup.objective_markers
                if marker.objective_marker_id == target_objective_id
            )
        target_id = target_marker.objective_marker_id
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                target_marker,
                offsets=((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
            )
        )
        if target_objective_id is None:
            additional_targets = tuple(
                marker
                for marker in state.mission_setup.objective_markers
                if marker.objective_role is ObjectiveMarkerRole.CENTRAL
                and marker.objective_marker_id != target_id
            )
            assert len(additional_targets) >= len(units) - 1
            for additional_unit, additional_target in zip(
                units[1:], additional_targets[: len(units) - 1], strict=True
            ):
                additional_placement = state.battlefield_state.unit_placement_by_id(
                    additional_unit.unit_instance_id
                )
                state.battlefield_state = state.battlefield_state.with_unit_placement(
                    with_model_offsets(
                        additional_placement,
                        additional_target,
                        offsets=(
                            (0.0, 0.0),
                            (1.0, 0.0),
                            (2.0, 0.0),
                            (0.0, 1.0),
                            (1.0, 1.0),
                        ),
                    )
                )
    decisions = DecisionController()
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id=player_id,
        mission_action_id=mission_action_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.decision_request is not None
    request = status.decision_request
    selected_option = next(
        option
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
        and cast(dict[str, JsonValue], option.payload)["unit_instance_id"] == unit.unit_instance_id
        and cast(dict[str, JsonValue], option.payload)["target_id"] == target_id
    )
    result = DecisionResult.for_request(
        result_id=f"phase17n-action-result:{mission_action_id}:{player_id}",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(result)
    action = state.mission_action_states[-1]
    state.battle_phase_index = state.battle_phase_sequence.index(current_phase)
    return state, decisions, action, target_id


def phase17n_action_turn_end_record(
    *,
    state: GameState,
    decisions: DecisionController,
    controlled_target_id: str,
    action: MissionActionState,
) -> ObjectiveControlRecord:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    if controlled_target_id != action.target_id:
        raise AssertionError("Primary Action turn-end target drifted.")
    resolved = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    state.record_objective_control_record(resolved)
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "record_ids": [resolved.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    return resolved


def append_authenticated_normal_move(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    suffix: str,
    pose_transform: Callable[[Pose], Pose],
) -> None:
    """Apply one replay-authenticated normal move to a Phase 17N fixture."""

    battlefield = state.battlefield_state
    active_player_id = state.active_player_id
    assert battlefield is not None
    assert active_player_id is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    model_paths = tuple(
        (row.model_instance_id, (row.pose, pose_transform(row.pose)))
        for row in placement.model_placements
    )
    witness = PathWitness.for_paths(model_paths)
    action_request = DecisionRequest(
        request_id=f"phase17n-authority-move-action-{suffix}",
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=active_player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "active_player_id": active_player_id,
                "unit_instance_id": unit_instance_id,
            }
        ),
        options=(
            DecisionOption(
                option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
                label="Normal Move",
                payload=validate_json_value(
                    {
                        "unit_instance_id": unit_instance_id,
                        "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
                        "movement_mode": "normal",
                    }
                ),
            ),
        ),
    )
    decisions.request_decision(action_request)
    action_result = DecisionResult.for_request(
        result_id=f"phase17n-authority-move-action-result-{suffix}",
        request=action_request,
        selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
    )
    decisions.submit_result(action_result)
    proposal_request = MovementProposalRequest(
        request_id=f"phase17n-authority-move-proposal-{suffix}",
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=active_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=ProposalKind.NORMAL_MOVE,
        source_decision_request_id=action_request.request_id,
        source_decision_result_id=action_result.result_id,
        spatial_context_hash="0" * 64,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        context={"movement_mode": "normal"},
    )
    proposal_decision_request = proposal_request.to_decision_request()
    decisions.request_decision(proposal_decision_request)
    proposal_result = DecisionResult(
        result_id=f"phase17n-authority-move-proposal-result-{suffix}",
        request_id=proposal_decision_request.request_id,
        decision_type=proposal_decision_request.decision_type,
        actor_id=active_player_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=ProposalKind.NORMAL_MOVE,
                unit_instance_id=unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
                witness=witness,
                movement_mode="normal",
            ).to_payload()
        ),
    )
    decisions.submit_result(proposal_result)
    transition = BattlefieldTransitionBatch(
        displacements=tuple(
            ModelDisplacementRecord(
                model_instance_id=model_id,
                displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
                start_pose=poses[0],
                end_pose=poses[-1],
                path_witness=PathWitness.for_paths(((model_id, poses),)),
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
            )
            for model_id, poses in model_paths
        )
    )
    decisions.event_log.append(
        "movement_activation_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_instance_id,
            "request_id": action_request.request_id,
            "result_id": action_result.result_id,
            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
            "movement_mode": "normal",
            "witness": witness.to_payload(),
            "transition_batch": transition.to_payload(),
            "displacement_kind": ModelDisplacementKind.NORMAL_MOVE.value,
        },
    )
    state.battlefield_state = battlefield.with_unit_placement(
        placement.with_model_placements(
            tuple(row.with_pose(pose_transform(row.pose)) for row in placement.model_placements)
        )
    )


def phase17n_action_opportunity_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    state = _action_ready_state()
    decisions = DecisionController()
    status = request_mission_action_opportunity(
        state=state,
        decisions=decisions,
        player_id="player-b",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status is not None
    assert status.decision_request is not None
    request = status.decision_request
    assert any(
        option.option_id == DECLINE_MISSION_ACTION_START_OPTION_ID for option in request.options
    )
    assert any(option.option_id.startswith("start:maintain-control:") for option in request.options)
    return state, decisions, request


def phase17n_accepted_action_opportunity_decline_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
    DecisionResult,
]:
    state, decisions, request = phase17n_action_opportunity_fixture()
    result = DecisionResult.for_request(
        result_id=f"{request.request_id}:decline-result",
        request=request,
        selected_option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
    )
    record = decisions.submit_result(result)
    apply_mission_decision(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    return state, decisions, request, result


def phase17n_direct_action_pending_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    state = _action_ready_state()
    decisions = DecisionController()
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id="player-b",
        mission_action_id="maintain-control",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.decision_request is not None
    return state, decisions, status.decision_request


def phase17n_locate_pending_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    setup = phase17n_event_setup(
        layout_id="disruption-vs-priority-assets-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=None,
        phase=None,
        battle_round=0,
    )
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = len(state.setup_sequence) - 1
    decisions = DecisionController()
    request = locate_and_deny_setup_choice_request(state=state, decisions=decisions)
    assert request is not None
    decisions.request_decision(request)
    return state, decisions, request


def phase17n_punishment_pending_fixture(
    *,
    attacker_player_id: str = "player-a",
    defender_player_id: str = "player-b",
    owner_player_id: str = "player-a",
    battle_round: int = 1,
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_b_units: tuple[UnitMusterSelection, ...] | None = None,
    attach_first_two_enemy_units: bool = False,
) -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    setup = phase17n_event_setup(
        layout_id="purge-the-foe-vs-disruption-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="disruption",
        attacker_player_id=attacker_player_id,
        defender_player_id=defender_player_id,
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=owner_player_id,
        phase=BattlePhase.COMMAND,
        battle_round=battle_round,
        player_a_units=player_a_units,
        player_b_units=player_b_units,
    )
    assert state.battlefield_state is not None
    target = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    enemy_player_id = next(
        player_id for player_id in state.player_ids if player_id != owner_player_id
    )
    enemies = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == enemy_player_id
        for unit in army.units
    )
    contributions: list[ObjectiveControlContribution] = []
    for enemy_index, enemy in enumerate(enemies):
        placement = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
        x_shift = float(enemy_index) * 3.0
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                target,
                offsets=(
                    (x_shift, 0.0),
                    (x_shift + 1.0, 0.0),
                    (x_shift + 2.0, 0.0),
                    (x_shift, 1.0),
                    (x_shift + 1.0, 1.0),
                ),
            )
        )
        contributions.append(
            ObjectiveControlContribution(
                player_id=enemy_player_id,
                unit_instance_id=enemy.unit_instance_id,
                model_instance_id=enemy.own_models[0].model_instance_id,
                objective_control=1,
                effective_objective_control=1,
                battle_shocked=False,
                horizontal_distance_inches=0.0,
                vertical_gap_inches=0.0,
            )
        )
    if attach_first_two_enemy_units:
        _attach_first_two_enemy_units(state, enemy_player_id=enemy_player_id)
    record = ObjectiveControlRecord(
        record_id=(
            f"phase17n-pending-punishment-turn-start-record-{battle_round:02d}-{owner_player_id}"
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=owner_player_id,
        timing=ObjectiveControlTiming.TURN_START,
        phase=BattlePhase.COMMAND.value,
        battlefield_id=state.battlefield_state.battlefield_id,
        results=tuple(
            ObjectiveControlResult.from_contributors(
                objective_id=marker.objective_marker_id,
                contributors=(
                    tuple(contributions)
                    if marker.objective_marker_id == target.objective_marker_id
                    else ()
                ),
            )
            for marker in setup.objective_markers
        ),
    )
    round_token = f"round-{battle_round:02d}"
    objective_state = PrimaryObjectiveTurnStartState(
        state_id=f"primary-turn-start:{state.game_id}:{round_token}:{owner_player_id}",
        game_id=state.game_id,
        player_id=owner_player_id,
        active_player_id=owner_player_id,
        battle_round=state.battle_round,
        source_objective_control_record=record,
        controlled_objective_ids=(),
        source_id=f"{state.game_id}:primary-turn-start:{round_token}:{owner_player_id}",
    )
    snapshot = build_primary_rules_unit_turn_start_snapshot(state=state)
    state.primary_objective_turn_start_states = [objective_state]
    state.primary_rules_unit_turn_start_snapshots = [snapshot]
    decisions = DecisionController()
    record_primary_turn_start_evidence_event(
        event_log=decisions.event_log,
        objective_state=objective_state,
        position_snapshot=snapshot,
    )
    request = punishment_choice_request(state=state, decisions=decisions)
    assert request is not None
    decisions.request_decision(request)
    _record_battle_primary_choice_requested(state=state, decisions=decisions, request=request)
    return state, decisions, request


def _attach_first_two_enemy_units(state: GameState, *, enemy_player_id: str) -> None:
    enemy_army = next(army for army in state.army_definitions if army.player_id == enemy_player_id)
    if len(enemy_army.units) < 2:
        raise AssertionError("Attached Punishment fixture requires two enemy units.")
    bodyguard = enemy_army.units[0]
    leader = enemy_army.units[1]
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    attached_id = f"attached-unit:{enemy_army.army_id}:phase17n-step5d-condemned"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=component_ids,
        source_id="phase17n-step5d-attached-source",
        attachment_source_ids=("phase17n-step5d-attachment-rule",),
    )
    unit_by_id = {unit.unit_instance_id: unit for unit in enemy_army.units}
    state.army_definitions = [
        replace(army, attached_units=(formation,)) if army.player_id == enemy_player_id else army
        for army in state.army_definitions
    ]
    state.starting_strength_records = sorted(
        (
            record
            for record in state.starting_strength_records
            if record.unit_instance_id not in component_ids
        ),
        key=lambda record: record.unit_instance_id,
    )
    state.starting_strength_records.append(
        StartingStrengthRecord(
            player_id=enemy_player_id,
            unit_instance_id=attached_id,
            starting_model_count=sum(
                len(unit_by_id[component_id].own_models) for component_id in component_ids
            ),
            single_model_starting_wounds=None,
            source_id=formation.source_id,
        )
    )
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    state.starting_attached_unit_records = [
        StartingAttachedUnitRecord.from_formation(
            player_id=enemy_player_id,
            attached_unit=formation,
            unit_by_id=unit_by_id,
        )
    ]


def phase17n_consecrate_pending_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    setup = phase17n_event_setup(
        layout_id="purge-the-foe-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="reconnaissance",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.SHOOTING,
        battle_round=1,
    )
    decisions = DecisionController()
    friendly = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    enemy = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    target = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    assert state.battlefield_state is not None
    friendly_placement = state.battlefield_state.unit_placement_by_id(friendly.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            friendly_placement,
            target,
            offsets=((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        )
    )
    _record_empty_current_turn_start_evidence(state=state, decisions=decisions)
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=friendly.unit_instance_id,
    )
    destroyed_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=enemy.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=friendly.unit_instance_id,
        source_model_instance_id=friendly.own_models[0].model_instance_id,
    )
    destroyed_model_ids = enemy.own_model_ids()
    departures: list[PrimaryBattlefieldDepartureState] = []
    model_events: list[EventRecord] = []
    for model_id in destroyed_model_ids:
        model_event = decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "model_instance_id": model_id,
                "target_unit_instance_id": enemy.unit_instance_id,
                "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
                "destroyed_rules_unit_objective_proximity_witness": (
                    destroyed_witness.to_payload()
                ),
                **attribution.to_payload(),
            },
        )
        model_events.append(model_event)
        destroy_model_by_rule(state=state, model_instance_id=model_id)
        model_departures = record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id=(f"core-rules:primary-unit-destruction-tracking:{model_event.event_id}"),
            occurrence_id=model_event.event_id,
        )
        departures.extend(model_departures)
        for departure in model_departures:
            record_primary_battlefield_departure_event(
                event_log=decisions.event_log,
                departure=departure,
            )
    model_event = model_events[-1]
    source_id = f"core-rules:primary-unit-destruction-tracking:{model_event.event_id}"
    destruction_ids_before = tuple(
        destruction.destruction_id for destruction in state.primary_unit_destruction_states
    )
    state.record_primary_unit_destruction(
        destruction_attribution=attribution,
        source_model_destroyed_event_id=model_event.event_id,
        source_rules_unit_objective_proximity_witness=source_witness,
        source_battlefield_departure_ids=tuple(departure.departure_id for departure in departures),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=enemy.unit_instance_id,
        source_id=f"{source_id}:{enemy.unit_instance_id}",
    )
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=decisions.event_log,
        destruction_ids_before=destruction_ids_before,
    )
    _enter_turn_end(state)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    _record_turn_end_objective_boundary(decisions=decisions, record=record)
    request = consecrate_choice_request(state=state, decisions=decisions)
    assert request is not None
    decisions.request_decision(request)
    _record_battle_primary_choice_requested(state=state, decisions=decisions, request=request)
    mark_pending_primary_scoring_boundaries(
        state=state,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_PRIMARY_MISSION_CHOICE,
        pending_decision_request_id=request.request_id,
    )
    return state, decisions, request


def phase17n_sensor_pending_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
]:
    state, decisions, locate_request = phase17n_locate_pending_fixture()
    locate_result = DecisionResult.for_request(
        result_id=f"{locate_request.request_id}:result",
        request=locate_request,
        selected_option_id=locate_request.options[0].option_id,
    )
    decisions.submit_result(locate_result)
    assert apply_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=locate_request,
        result=locate_result,
    )

    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.replace_shooting_phase_state(
        ShootingPhaseState(battle_round=1, active_player_id="player-a")
    )
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    target = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            target,
            offsets=((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8)),
        )
    )
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id="player-a",
        mission_action_id="sensor-sweep-locate-and-deny",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.decision_request is not None
    action_request = status.decision_request
    action_result = DecisionResult.for_request(
        result_id=f"{action_request.request_id}:result",
        request=action_request,
        selected_option_id=action_request.options[0].option_id,
    )
    action_record = decisions.submit_result(action_result)
    apply_mission_decision(
        state=state,
        request=action_record.request,
        result=action_result,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    action = state.mission_action_states[-1]
    _enter_turn_end(state)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    _record_turn_end_objective_boundary(decisions=decisions, record=record)
    completed = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(completed) == 1
    assert completed[0].action_id == action.action_id
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    request = sensor_sweep_marker_removal_choice_request(
        state=state,
        decisions=decisions,
        action_id=action.action_id,
    )
    assert request is not None
    decisions.request_decision(request)
    _record_battle_primary_choice_requested(state=state, decisions=decisions, request=request)
    return state, decisions, request


def _action_ready_state() -> GameState:
    setup = phase17n_event_setup(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.SHOOTING,
        battle_round=1,
    )
    state.replace_shooting_phase_state(
        ShootingPhaseState(battle_round=1, active_player_id="player-b")
    )
    assert state.battlefield_state is not None
    unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    target = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            target,
            offsets=((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8)),
        )
    )
    return state


def phase17n_state_with_setup(
    *,
    setup: MissionSetup,
    active_player_id: str | None,
    phase: BattlePhase | None,
    battle_round: int,
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_b_units: tuple[UnitMusterSelection, ...] | None = None,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
) -> GameState:
    state = battle_state(
        player_a_units=player_a_units,
        player_b_units=player_b_units,
        player_a_secondary=player_a_secondary,
    )
    state.mission_setup = setup
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                setup.primary_mission_assignment_for_player(army.player_id).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = battle_round
    state.active_player_id = active_player_id
    state.battle_phase_index = None if phase is None else state.battle_phase_sequence.index(phase)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    return state


def _enter_turn_end(state: GameState) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.replace_shooting_phase_state(None)


def _record_turn_end_objective_boundary(
    *,
    decisions: DecisionController,
    record: ObjectiveControlRecord,
) -> None:
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )


def _record_empty_current_turn_start_evidence(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    assert state.active_player_id is not None
    record = ObjectiveControlRecord(
        record_id=(
            f"objective-control:round-{state.battle_round:02d}:"
            f"{state.active_player_id}:{BattlePhase.COMMAND.value}:"
            f"{ObjectiveControlTiming.TURN_START.value}"
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        timing=ObjectiveControlTiming.TURN_START,
        phase=BattlePhase.COMMAND.value,
        battlefield_id=state.battlefield_state.battlefield_id,
        results=tuple(
            ObjectiveControlResult.from_contributors(
                objective_id=marker.objective_marker_id,
                contributors=(),
            )
            for marker in state.mission_setup.objective_markers
        ),
    )
    objective_state = PrimaryObjectiveTurnStartState(
        state_id=(
            f"primary-turn-start:{state.game_id}:round-{state.battle_round:02d}:"
            f"{state.active_player_id}"
        ),
        game_id=state.game_id,
        player_id=state.active_player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        source_objective_control_record=record,
        controlled_objective_ids=(),
        source_id=(
            f"{state.game_id}:primary-turn-start:round-{state.battle_round:02d}:"
            f"{state.active_player_id}"
        ),
    )
    snapshot = build_primary_rules_unit_turn_start_snapshot(state=state)
    state.primary_objective_turn_start_states = [objective_state]
    state.primary_rules_unit_turn_start_snapshots = [snapshot]
    record_primary_turn_start_evidence_event(
        event_log=decisions.event_log,
        objective_state=objective_state,
        position_snapshot=snapshot,
    )


def _record_battle_primary_choice_requested(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
) -> None:
    assert state.current_battle_phase is not None
    decisions.event_log.append(
        "primary_mission_choice_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": state.current_battle_phase.value,
            "request_id": request.request_id,
            "decision_type": request.decision_type,
            "actor_id": request.actor_id,
        },
    )


__all__ = (
    "append_authenticated_normal_move",
    "phase17n_accepted_action_opportunity_decline_fixture",
    "phase17n_action_opportunity_fixture",
    "phase17n_action_turn_end_record",
    "phase17n_consecrate_pending_fixture",
    "phase17n_direct_action_pending_fixture",
    "phase17n_event_setup",
    "phase17n_locate_pending_fixture",
    "phase17n_punishment_pending_fixture",
    "phase17n_sensor_pending_fixture",
    "phase17n_started_primary_action_fixture",
)
