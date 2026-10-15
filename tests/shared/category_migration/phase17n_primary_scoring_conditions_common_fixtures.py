from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_conditions_bindings import (
    AttachedUnitFormation,
    BattlePhase,
    DecisionController,
    DecisionRequest,
    DecisionResult,
    GameLifecycle,
    GameLifecycleStage,
    GameState,
    MissionSetup,
    ObjectiveControlResult,
    Pose,
    PrimaryObjectiveTurnStartState,
    StartingAttachedUnitRecord,
    StartingStrengthRecord,
    apply_primary_mission_choice,
    build_primary_rules_unit_turn_start_snapshot,
    pytest,
    replace,
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.fixture(scope="module")
def battlefield_dominance_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-1",
        terrain_layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


@pytest.fixture(scope="module")
def purge_and_secure_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
        terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="reconnaissance",
    )


def _phase17n_event_setup(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
) -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id=f"mission-{layout_id}",
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_player_id="player-b",
        defender_force_disposition_id=defender_force_disposition_id,
    )


def _phase17n_submit_primary_mission_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> bool:
    decisions.request_decision(request)
    if state.stage is GameLifecycleStage.SETUP:
        decisions.submit_result(result)
        return apply_primary_mission_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(result)
    return True


def _phase17n_clear_turn_start_contributors(state: GameState) -> None:
    evidence = state.primary_objective_turn_start_states[0]
    record = replace(
        evidence.source_objective_control_record,
        record_id="phase17n-punishment-empty-turn-start-record",
        results=tuple(
            ObjectiveControlResult.from_contributors(
                objective_id=result.objective_id,
                contributors=(),
            )
            for result in evidence.source_objective_control_record.results
        ),
    )
    state.primary_objective_turn_start_states = [
        PrimaryObjectiveTurnStartState(
            state_id="phase17n-punishment-empty-turn-start-state",
            game_id=state.game_id,
            player_id="player-a",
            active_player_id="player-a",
            battle_round=state.battle_round,
            source_objective_control_record=record,
            controlled_objective_ids=(),
            source_id="phase17n-punishment-empty-turn-start-source",
        )
    ]


def _phase17n_refresh_turn_start_snapshot(state: GameState) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=state.mission_setup.battlefield_depth_inches,
        terrain_features=state.mission_setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                state.mission_setup.primary_mission_assignment_for_player(
                    army.player_id
                ).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.primary_rules_unit_turn_start_snapshots = [
        build_primary_rules_unit_turn_start_snapshot(state=state)
    ]


def _phase17n_enter_battle_turn_end(state: GameState, *, active_player_id: str) -> None:
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = active_player_id


def _phase17n_set_model_wounds(
    state: GameState,
    *,
    model_ids: tuple[str, ...],
    wounds_remaining: int,
) -> None:
    requested_ids = set(model_ids)
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        if model.model_instance_id in requested_ids
                        else model
                        for model in unit.own_models
                    ),
                )
                if requested_ids.intersection(unit.own_model_ids())
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]


def _phase17n_attach_test_leader(
    *,
    state: GameState,
    bodyguard_id: str,
) -> tuple[str, tuple[str, ...]]:
    army = next(army for army in state.army_definitions if army.player_id == "player-b")
    bodyguard = next(unit for unit in army.units if unit.unit_instance_id == bodyguard_id)
    leader_id = f"{army.army_id}:phase17n-surveil-leader"
    leader = replace(
        bodyguard,
        unit_instance_id=leader_id,
        name="Phase 17N Surveil Leader",
        own_models=tuple(
            replace(
                model,
                model_instance_id=f"{leader_id}:model-{index:03d}",
                name=f"Phase 17N Surveil Leader {index}",
            )
            for index, model in enumerate(bodyguard.own_models, start=1)
        ),
    )
    attached_id = f"attached-unit:{army.army_id}:phase17n-surveil-unit"
    component_ids = tuple(sorted((bodyguard_id, leader_id)))
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard_id,
        leader_unit_instance_ids=(leader_id,),
        component_unit_instance_ids=component_ids,
        source_id="phase17n-surveil-attached-source",
        attachment_source_ids=("phase17n-surveil-leader-source",),
    )
    state.army_definitions = [
        replace(candidate, units=(*candidate.units, leader), attached_units=(formation,))
        if candidate.player_id == "player-b"
        else candidate
        for candidate in state.army_definitions
    ]
    state.starting_strength_records = [
        record
        for record in state.starting_strength_records
        if record.unit_instance_id not in component_ids
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord(
            player_id="player-b",
            unit_instance_id=attached_id,
            starting_model_count=len(bodyguard.own_models) + len(leader.own_models),
            single_model_starting_wounds=None,
            source_id=formation.source_id,
        )
    )
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    state.starting_attached_unit_records = [
        *state.starting_attached_unit_records,
        StartingAttachedUnitRecord.from_formation(
            player_id="player-b",
            attached_unit=formation,
            unit_by_id={unit.unit_instance_id: unit for unit in (*army.units, leader)},
        ),
    ]
    assert state.battlefield_state is not None
    bodyguard_placement = state.battlefield_state.unit_placement_by_id(bodyguard_id)
    leader_placement = replace(
        bodyguard_placement,
        unit_instance_id=leader_id,
        model_placements=tuple(
            replace(
                placement,
                unit_instance_id=leader_id,
                model_instance_id=leader.own_models[index].model_instance_id,
                pose=Pose.at(
                    placement.pose.position.x,
                    placement.pose.position.y + 4.0,
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
            for index, placement in enumerate(bodyguard_placement.model_placements)
        ),
    )
    state.battlefield_state = state.battlefield_state.with_added_unit_placement(leader_placement)
    _phase17n_refresh_turn_start_snapshot(state)
    return attached_id, component_ids


def _phase17n_move_attached_components_away(
    *,
    state: GameState,
    component_ids: tuple[str, ...],
) -> None:
    assert state.battlefield_state is not None
    for component_index, component_id in enumerate(component_ids):
        placement = state.battlefield_state.unit_placement_by_id(component_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            2.0 + component_index + (model_index * 0.4),
                            2.0,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for model_index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )


__all__: list[str] = []
__all__ += ["AttachedUnitFormation", "BattlePhase", "DecisionController", "DecisionRequest"]
__all__ += ["DecisionResult", "GameLifecycle", "GameLifecycleStage", "GameState", "MissionSetup"]
__all__ += ["ObjectiveControlResult", "Pose", "PrimaryObjectiveTurnStartState"]
__all__ += ["StartingAttachedUnitRecord", "StartingStrengthRecord"]
__all__ += ["_phase17n_attach_test_leader", "_phase17n_clear_turn_start_contributors"]
__all__ += ["_phase17n_enter_battle_turn_end", "_phase17n_event_setup"]
__all__ += ["_phase17n_move_attached_components_away", "_phase17n_refresh_turn_start_snapshot"]
__all__ += ["_phase17n_set_model_wounds", "_phase17n_submit_primary_mission_choice"]
__all__ += ["apply_primary_mission_choice", "battlefield_dominance_setup"]
__all__ += ["build_primary_rules_unit_turn_start_snapshot", "purge_and_secure_setup", "pytest"]
__all__ += ["replace", "warhammer_event_companion_2026_07_mission_pack"]
