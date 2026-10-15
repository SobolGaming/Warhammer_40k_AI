from __future__ import annotations

from tests.shared.category_migration.phase11e_mission_scoring_cleanup_bindings import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    START_MISSION_ACTION_DECISION_TYPE,
    STRATAGEM_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    ArmyDefinition,
    BattlefieldRegionKind,
    BattlePhase,
    Characteristic,
    CharacteristicValue,
    DecisionController,
    DecisionResult,
    DiceRollManager,
    FiniteOptionSubmission,
    GameLifecycle,
    GameState,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    LocalGameSession,
    MissionActionState,
    MissionLogicalTerrainArea,
    MissionSetup,
    ModelInstance,
    MovementDiceRecord,
    MovementPhaseActionKind,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerRole,
    RuntimeModifierRegistry,
    SecondaryMissionMode,
    UnitInstance,
    cast,
    drain_pending_secondary_mission_setup,
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
    mission_pack_for_id,
    record_new_primary_turn_start_evidence_events,
    replace,
    request_mission_action_start,
    rules_unit_view_by_id,
    with_unit_keywords,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_configuration import (
    _battle_state,
    _battle_state_from_config,
    _config,
    _config_for_primary,
    _config_with_player_a_vehicle,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_state_primitives import (
    _place_unit_near_point,
    _with_model_offsets,
)


def _event_binds_objective_control_record(event: JsonValue, record_id: str) -> bool:
    if not isinstance(event, dict):
        return False
    payload = event["payload"]
    if not isinstance(payload, dict):
        return False
    if event["event_type"] == "end_boundary_objective_control_determined":
        return payload.get("record_ids") == [record_id]
    if event["event_type"] == "primary_scoring_commit_checkpoint_recorded":
        return payload.get("objective_control_record_id") == record_id
    return False


def _first_plunderable_logical_terrain_area(
    state: GameState,
    *,
    player_id: str,
) -> MissionLogicalTerrainArea:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    return next(
        area
        for area in mission_logical_terrain_areas(state.mission_setup)
        if not logical_terrain_area_within_player_territory(
            area,
            mission_setup=state.mission_setup,
            player_id=player_id,
        )
    )


def _record_completed_zero_vp_mission_action(
    state: GameState,
    *,
    mission_action_id: str,
    action_id: str,
    target_id: str,
    player_id: str = "player-a",
) -> str:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    mission_action = mission_pack_for_id(state.mission_setup.mission_pack_id).mission_action(
        mission_action_id
    )
    army = next(army for army in state.army_definitions if army.player_id == player_id)
    unit_instance_id = army.units[0].unit_instance_id
    started = MissionActionState.start(
        action_id=action_id,
        mission_action_id=mission_action.mission_action_id,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=target_id,
        mission_id=mission_action.mission_id,
        battle_round=state.battle_round,
        phase=mission_action.start_phase,
        start_timing=mission_action.start_timing,
        completion_timing=mission_action.completion_timing,
        eligible_unit_instance_ids=(unit_instance_id,),
        interruption_conditions=mission_action.interruption_conditions,
        scoring_source_id=mission_action.scoring_source_id,
        victory_points=mission_action.victory_points,
    )
    completion_phase = (
        BattlePhase.FIGHT.value
        if mission_action.completion_timing == "turn_end"
        else mission_action.start_phase
    )
    completed = started.complete_without_award(
        battle_round=state.battle_round,
        phase=completion_phase,
        completion_timing=mission_action.completion_timing,
    )
    state.record_mission_action_state(completed)
    return mission_action.source_id


def _objective_logical_terrain_area(
    mission_setup: MissionSetup,
    *,
    objective_role: ObjectiveMarkerRole,
) -> MissionLogicalTerrainArea:
    marker = next(
        marker
        for marker in mission_setup.objective_markers
        if marker.objective_role is objective_role
    )
    association = next(
        association
        for association in mission_setup.objective_terrain_areas
        if association.objective_marker_id == marker.objective_marker_id
    )
    physical_areas_by_id = {area.terrain_area_id: area for area in mission_setup.terrain_areas}
    logical_ids = {
        physical_areas_by_id[area_id].logical_terrain_area_id
        for area_id in association.terrain_area_ids
    }
    assert len(logical_ids) == 1
    (logical_id,) = logical_ids
    return next(
        area
        for area in mission_logical_terrain_areas(mission_setup)
        if area.logical_terrain_area_id == logical_id
    )


def _logical_terrain_area_test_point(
    area: MissionLogicalTerrainArea,
) -> tuple[float, float]:
    point = area.members[0].footprint_polygon[0]
    return point.x_inches, point.y_inches


def _mission_action_state(
    *,
    action_id: str,
    target_id: str = "take-and-hold-vs-purge-the-foe-layout-3-center-central",
) -> MissionActionState:
    return MissionActionState.start(
        action_id=action_id,
        mission_action_id="cleanse-objective",
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id=target_id,
        condition_target_id=target_id,
        mission_id="cleanse",
        battle_round=1,
        phase=BattlePhase.MOVEMENT.value,
        start_timing="movement_phase_unit_selected",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=("unit_moved",),
        scoring_source_id="cleanse",
        victory_points=5,
    )


def _complete_shooting_for_action_test(lifecycle: GameLifecycle, *, unit_instance_id: str) -> None:
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from warhammer40k_core.engine.event_log import validate_json_value

    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    target_id = state.army_definitions[1].units[0].unit_instance_id
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    placement = state.battlefield_state.unit_placement_by_id(
        rules_unit.component_unit_instance_ids[0]
    )
    origin = placement.model_placements[0].pose.position
    state.battlefield_state = replace(state.battlefield_state, terrain_features=())
    _place_unit_near_point(
        state, unit_instance_id=target_id, x_inches=origin.x + 12.0, y_inches=origin.y
    )
    for unit in state.army_definitions[0].units:
        if unit.unit_instance_id not in rules_unit.component_unit_instance_ids:
            _place_unit_near_point(
                state,
                unit_instance_id=unit.unit_instance_id,
                x_inches=origin.x,
                y_inches=origin.y + 6.0,
            )
    session = LocalGameSession(lifecycle=lifecycle)
    for index in range(100):
        shooting = state.shooting_phase_state
        if (
            shooting is not None
            and unit_instance_id in shooting.shot_unit_ids
            and shooting.attack_sequence is None
            and shooting.pending_completed_attack_sequence is None
        ):
            return
        request = pending_request(session)
        if request.decision_type == START_MISSION_ACTION_DECISION_TYPE:
            option_id = DECLINE_MISSION_ACTION_START_OPTION_ID
        elif request.decision_type == "select_shooting_unit":
            option_id = unit_instance_id
        elif request.decision_type == "select_shooting_type":
            option_id = "normal"
        elif request.decision_type == "submit_shooting_declaration":
            proposal = _proposal_from_request(request=request, target_unit_id=target_id)
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"order34-fixture-shot:{index}",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            continue
        else:
            submit_fixture_request(session, request)
            continue
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"order34-fixture-shot:{index}",
            option_id=option_id,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("Action fixture shooting did not complete within its decision budget")


def _attached_cleanse_action(
    *,
    state: GameState,
    action_id: str,
) -> MissionActionState:
    return MissionActionState.start(
        action_id=action_id,
        mission_action_id="cleanse-objective",
        player_id="player-a",
        unit_instance_id="attached-unit:army-alpha:bodyguard-unit",
        target_id=_center_marker_definition(state).objective_marker_id,
        condition_target_id=_center_marker_definition(state).objective_marker_id,
        mission_id="cleanse",
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING.value,
        start_timing="shooting_phase",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("attached-unit:army-alpha:bodyguard-unit",),
        interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
        scoring_source_id="cleanse",
        victory_points=0,
    )


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    return _objective_marker_definition(state, "center")


def _objective_marker_definition(
    state: GameState,
    target_suffix: str,
) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if _objective_marker_matches_suffix(marker.objective_marker_id, target_suffix):
            return marker
    raise AssertionError(f"missing {target_suffix} objective marker")


def _start_mission_action_via_lifecycle(
    *,
    lifecycle: GameLifecycle,
    target_suffix: str,
    result_id: str,
    unit_instance_id: str = "army-alpha:intercessor-unit-1",
) -> MissionActionState:
    state = lifecycle.state
    assert state is not None
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_instance_id,
        target_suffix=target_suffix,
    )
    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if _objective_marker_matches_suffix(
            str(cast(dict[str, JsonValue], option.payload)["target_id"]),
            target_suffix,
        )
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id=result_id,
    ).to_result(request)
    lifecycle.submit_decision(result)
    action_id = f"mission-action:{result_id}"
    return state.mission_action_state_by_id(action_id)


def _place_unit_near_objective(
    state: GameState,
    *,
    unit_instance_id: str,
    target_suffix: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if _objective_marker_matches_suffix(marker.objective_marker_id, target_suffix)
    )
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    offsets = tuple(
        (2.0 + float(index), 0.0) for index in range(len(unit_placement.model_placements))
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit_placement, marker, offsets=offsets)
    )


def _record_missing_turn_start_evidence_events(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    recorded_occurrences = {
        (
            event.payload.get("game_id"),
            event.payload.get("active_player_id"),
            event.payload.get("battle_round"),
        )
        for event in decisions.event_log.records
        if event.event_type == "primary_turn_start_evidence_recorded"
        and isinstance(event.payload, dict)
    }
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=tuple(
            value.state_id
            for value in state.primary_objective_turn_start_states
            if (value.game_id, value.active_player_id, value.battle_round) in recorded_occurrences
        ),
        snapshot_ids_before=tuple(
            value.snapshot_id
            for value in state.primary_rules_unit_turn_start_snapshots
            if (value.game_id, value.active_player_id, value.battle_round) in recorded_occurrences
        ),
    )


def _decline_stratagem_window_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    current = drain_pending_secondary_mission_setup(
        lifecycle,
        status,
        result_id_prefix=f"{result_id}-secondary-setup",
    )
    request = current.decision_request
    if request is None or request.decision_type != STRATAGEM_DECISION_TYPE:
        return current
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _battle_lifecycle(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
    mission_setup: MissionSetup | None = None,
) -> GameLifecycle:
    config = _config(mission_setup=mission_setup)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state(
        player_a_secondary=player_a_secondary,
        player_b_secondary=player_b_secondary,
        player_a_fixed_mission_ids=player_a_fixed_mission_ids,
        mission_setup=mission_setup,
        decisions=lifecycle.decision_controller,
    )
    return lifecycle


def _battle_lifecycle_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> GameLifecycle:
    config = _config_for_primary(
        primary_mission_id,
        objective_terrain_feature_id=objective_terrain_feature_id,
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    return lifecycle


def _battle_lifecycle_with_player_a_vehicle() -> GameLifecycle:
    config = _config_with_player_a_vehicle()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    return lifecycle


def _controlled_objective_result(
    objective_id: str,
    *,
    player_id: str,
) -> ObjectiveControlResult:
    return ObjectiveControlResult(
        objective_id=objective_id,
        status=ObjectiveControlStatus.CONTROLLED,
        controlled_by_player_id=player_id,
        scores=(ObjectiveControlScore(player_id=player_id, score=1),),
    )


def _no_mans_land_non_home_objective_ids(
    mission_setup: MissionSetup,
    *,
    player_id: str,
) -> tuple[str, ...]:
    nml_regions = tuple(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.NO_MANS_LAND
    )
    if not nml_regions:
        raise AssertionError("Event Companion fixture is missing a No Man's Land region.")
    home_role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if player_id == mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    home_ids = {
        marker.objective_marker_id
        for marker in mission_setup.objective_markers
        if marker.objective_role is home_role
    }
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_marker_id not in home_ids
            and any(
                region.contains_point(marker.x_inches, marker.y_inches) for region in nml_regions
            )
        )
    )


def _center_marker_definition_for_setup(
    mission_setup: MissionSetup,
) -> ObjectiveMarkerDefinition:
    for marker in mission_setup.objective_markers:
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL:
            return marker
    raise AssertionError("missing center objective marker")


def _objective_marker_matches_suffix(objective_marker_id: str, target_suffix: str) -> bool:
    return any(
        objective_marker_id.endswith(suffix)
        for suffix in _objective_marker_suffix_aliases(target_suffix)
    )


def _objective_marker_suffix_aliases(target_suffix: str) -> tuple[str, ...]:
    if target_suffix == "center":
        return (
            "-center",
            "-center-central",
            "-central-north",
            "-central-south",
            "-central-west",
            "-central-east",
        )
    if target_suffix in {"northeast", "northwest"}:
        return (f"-{target_suffix}", "-upper-central")
    if target_suffix in {"southeast", "southwest"}:
        return (f"-{target_suffix}", "-lower-central")
    return (target_suffix, f"-{target_suffix.replace('_', '-')}")


def _replace_unit(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    with_unit_keywords(unit, keywords=keywords)
                    if unit.unit_instance_id == unit_instance_id
                    else unit
                    for unit in army.units
                ),
            )
        )
    state.replace_army_definitions(updated_armies)


def _replace_unit_objective_control(
    state: GameState,
    *,
    unit_instance_id: str,
    objective_control: int | str,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                replacement = (
                    CharacteristicValue.source_dash(Characteristic.OBJECTIVE_CONTROL)
                    if objective_control == "-"
                    else CharacteristicValue.from_raw(
                        Characteristic.OBJECTIVE_CONTROL,
                        cast(int, objective_control),
                    )
                )
                updated_models.append(
                    replace(
                        model,
                        characteristics=tuple(
                            replacement
                            if value.characteristic is Characteristic.OBJECTIVE_CONTROL
                            else value
                            for value in model.characteristics
                        ),
                    )
                )
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.replace_army_definitions(updated_armies)


def _advanced_unit_state(*, unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:action-eligibility-advance",
        game_id="phase11e-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase11e-action-eligibility-advance").roll_fixed(
        request.spec,
        [3],
    )
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
    )


__all__: list[str] = []
__all__ += ["AdvanceRollRequest", "AdvanceRollResult", "AdvancedUnitState", "ArmyDefinition"]
__all__ += ["BattlePhase", "BattlefieldRegionKind", "Characteristic", "CharacteristicValue"]
__all__ += ["DECLINE_MISSION_ACTION_START_OPTION_ID", "DECLINE_STRATAGEM_WINDOW_OPTION_ID"]
__all__ += ["DecisionController", "DecisionResult", "DiceRollManager", "FiniteOptionSubmission"]
__all__ += ["GameLifecycle", "GameState", "JsonValue", "LifecycleStatus", "LifecycleStatusKind"]
__all__ += ["LocalGameSession", "MissionActionState", "MissionLogicalTerrainArea", "MissionSetup"]
__all__ += ["ModelInstance", "MovementDiceRecord", "MovementPhaseActionKind"]
__all__ += ["ObjectiveControlResult", "ObjectiveControlScore", "ObjectiveControlStatus"]
__all__ += ["ObjectiveMarkerDefinition", "ObjectiveMarkerRole", "RuntimeModifierRegistry"]
__all__ += ["START_MISSION_ACTION_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionMode", "UnitInstance", "_advanced_unit_state"]
__all__ += ["_attached_cleanse_action", "_battle_lifecycle", "_battle_lifecycle_for_primary"]
__all__ += ["_battle_lifecycle_with_player_a_vehicle", "_battle_state"]
__all__ += ["_battle_state_from_config", "_center_marker_definition"]
__all__ += ["_center_marker_definition_for_setup", "_complete_shooting_for_action_test"]
__all__ += ["_config", "_config_for_primary", "_config_with_player_a_vehicle"]
__all__ += ["_controlled_objective_result", "_decline_stratagem_window_if_pending"]
__all__ += ["_event_binds_objective_control_record", "_first_plunderable_logical_terrain_area"]
__all__ += ["_logical_terrain_area_test_point", "_mission_action_state"]
__all__ += ["_no_mans_land_non_home_objective_ids", "_objective_logical_terrain_area"]
__all__ += ["_objective_marker_definition", "_objective_marker_matches_suffix"]
__all__ += ["_objective_marker_suffix_aliases", "_place_unit_near_objective"]
__all__ += ["_place_unit_near_point", "_record_completed_zero_vp_mission_action"]
__all__ += ["_record_missing_turn_start_evidence_events", "_replace_unit"]
__all__ += ["_replace_unit_objective_control", "_start_mission_action_via_lifecycle"]
__all__ += ["_with_model_offsets", "cast", "drain_pending_secondary_mission_setup"]
__all__ += ["logical_terrain_area_within_player_territory", "mission_logical_terrain_areas"]
__all__ += ["mission_pack_for_id", "record_new_primary_turn_start_evidence_events", "replace"]
__all__ += ["request_mission_action_start", "rules_unit_view_by_id", "with_unit_keywords"]
