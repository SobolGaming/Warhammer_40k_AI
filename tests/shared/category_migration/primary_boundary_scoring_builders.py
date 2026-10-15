from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_boundary_lifecycle_bindings import (
    PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    ArmyCatalog,
    BattlePhase,
    DecisionController,
    GameConfig,
    GameLifecycle,
    GameLifecycleStage,
    GameState,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    Pose,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionMode,
    UnitPlacement,
    append_authenticated_normal_move,
    army_muster_request,
    complete_setup_through_gate,
    create_deterministic_battlefield_scenario,
    default_unit_selection,
    mustered_armies,
    phase11c_mission_setup,
    phase17n_event_setup,
    phase17n_state_with_setup,
    record_secondary_destruction_for_fixture,
    replace,
    ruleset,
    score_primary_objective_control_boundary,
    secondary_choice,
)
from tests.shared.category_migration.primary_boundary_state_and_geometry import (
    _add_unit_keyword,
    _destroy_first_model,
    _destroy_unit_with_events,
    _emit_oc_event,
    _first_unit,
    _place_player_on_role,
    _place_unit_interior_non_overlapping,
    _queue_pending_window,
    _return_destroyed_unit,
    _set_unit_starting_wounds,
)


def _pending_command_boundary_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=lifecycle.decision_controller, record=record)
    _queue_pending_window(
        lifecycle=lifecycle,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    )
    return lifecycle


def _pending_final_turn_end_boundary_lifecycle() -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-priority-assets-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.FIGHT,
        battle_round=5,
    )
    decisions = DecisionController()
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    _emit_oc_event(decisions=decisions, record=record)
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    _queue_pending_window(
        lifecycle=lifecycle,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    )
    return lifecycle


def _scored_command_boundary_after_mutation(*, kind: str) -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    enemy = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    original_placement: UnitPlacement | None = None
    if kind == "return_on_death":
        _place_unit_interior_non_overlapping(state, unit_instance_id=enemy.unit_instance_id)
        original_placement = _destroy_unit_with_events(
            state=state,
            decisions=decisions,
            unit_instance_id=enemy.unit_instance_id,
        )
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=decisions, record=record)
    if kind == "move":
        mover = next(
            unit
            for army in state.army_definitions
            if army.player_id == state.active_player_id
            for unit in army.units
        )
        append_authenticated_normal_move(
            state=state,
            decisions=decisions,
            unit_instance_id=mover.unit_instance_id,
            suffix="post-oc",
            pose_transform=lambda pose: Pose.at(
                pose.position.x,
                pose.position.y + 6.0,
                pose.position.z,
                facing_degrees=pose.facing.degrees,
            ),
        )
    elif kind == "destroy":
        _destroy_first_model(
            state=state, decisions=decisions, unit_instance_id=enemy.unit_instance_id
        )
    elif kind == "return_on_death":
        assert original_placement is not None
        _return_destroyed_unit(
            state=state,
            decisions=decisions,
            original_placement=original_placement,
        )
    else:
        raise AssertionError(f"unsupported mutation kind: {kind}")
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    return lifecycle


def _battlefield_dominance_lifecycle(
    *,
    phase: BattlePhase,
    battle_round: int,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
) -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=phase,
        battle_round=battle_round,
        player_a_secondary=player_a_secondary,
    )
    return GameLifecycle(state=state, decision_controller=DecisionController())


def _two_model_battlefield_dominance_lifecycle(
    *,
    phase: BattlePhase,
    battle_round: int,
) -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    canonical_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        canonical_catalog,
        datasheets=tuple(
            replace(
                datasheet,
                composition=tuple(
                    replace(composition, min_models=2) for composition in datasheet.composition
                ),
            )
            if datasheet.datasheet_id == "core-intercessor-like-infantry"
            else datasheet
            for datasheet in canonical_catalog.datasheets
        ),
    )
    target_selection = default_unit_selection("intercessor-unit-3")
    target_selection = replace(
        target_selection,
        model_profile_selections=tuple(
            replace(selection, model_count=2)
            for selection in target_selection.model_profile_selections
        ),
    )
    config = GameConfig(
        game_id="phase17n-partial-return-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(default_unit_selection("intercessor-unit-1"),),
            ),
            army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(target_selection,),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=phase11c_mission_setup(),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11c-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    complete_setup_through_gate(
        state=state,
        decisions=DecisionController(),
        config=config,
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
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    return GameLifecycle(state=state, decision_controller=DecisionController())


def _two_defender_battlefield_dominance_lifecycle(
    *,
    phase: BattlePhase,
    battle_round: int,
) -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = GameConfig(
        game_id="phase11c-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(default_unit_selection("intercessor-unit-1"),),
            ),
            army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(
                    default_unit_selection("intercessor-unit-3"),
                    default_unit_selection("intercessor-unit-4"),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=phase11c_mission_setup(),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11c-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )
    state.record_secondary_mission_choice(
        secondary_choice(player_id="player-b", mode=SecondaryMissionMode.FIXED)
    )
    complete_setup_through_gate(
        state=state,
        decisions=DecisionController(),
        config=config,
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
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    return GameLifecycle(state=state, decision_controller=DecisionController())


def _bring_it_down_player_a_scored_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    player_b_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        source_id="p2-bring-it-down-restore",
        event_log=lifecycle.decision_controller.event_log,
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    return lifecycle


def _two_player_bring_it_down_scored_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    player_a_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    player_b_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    _set_unit_starting_wounds(state, player_a_unit.unit_instance_id, wounds=10)
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-b",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        source_id="p2-bring-it-down-a",
        event_log=lifecycle.decision_controller.event_log,
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    state.active_player_id = "player-b"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-b",
        destroyed_unit_instance_id=player_a_unit.unit_instance_id,
        source_id="p2-bring-it-down-b",
        event_log=lifecycle.decision_controller.event_log,
    )
    state.score_secondary_mission_from_state(
        player_id="player-b",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    return lifecycle


def _same_boundary_two_player_bring_it_down_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    player_a_unit = _first_unit(state, player_id="player-a")
    player_b_unit = _first_unit(state, player_id="player-b")
    _set_unit_starting_wounds(state, player_a_unit.unit_instance_id, wounds=10)
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-b",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        source_id="evidence-swap-player-b-destroyed",
        event_log=lifecycle.decision_controller.event_log,
    )
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-b",
        destroyed_unit_instance_id=player_a_unit.unit_instance_id,
        source_id="evidence-swap-player-a-destroyed",
        event_log=lifecycle.decision_controller.event_log,
    )
    for player_id in ("player-a", "player-b"):
        state.score_secondary_mission_from_state(
            player_id=player_id,
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    return lifecycle


def _same_boundary_bring_it_down_and_assassination_lifecycle() -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    target = _first_unit(state, player_id="player-b")
    _set_unit_starting_wounds(state, target.unit_instance_id, wounds=10)
    _add_unit_keyword(state, target.unit_instance_id, keyword="CHARACTER")
    for secondary_mission_id in ("bring-it-down", "assassination"):
        state.record_secondary_mission_card_state(
            SecondaryMissionCardState.active_fixed(
                player_id="player-a",
                secondary_mission_id=secondary_mission_id,
            )
        )
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=target.unit_instance_id,
        source_id="evidence-swap-character-destroyed",
        event_log=lifecycle.decision_controller.event_log,
    )
    for secondary_mission_id in ("bring-it-down", "assassination"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    return lifecycle


def _single_mode_bring_it_down_lifecycle(mode: SecondaryMissionCardMode) -> GameLifecycle:
    lifecycle = _battlefield_dominance_lifecycle(
        phase=BattlePhase.FIGHT,
        battle_round=3,
        player_a_secondary=(
            SecondaryMissionMode.FIXED
            if mode is SecondaryMissionCardMode.FIXED
            else SecondaryMissionMode.TACTICAL
        ),
    )
    state = lifecycle.state
    assert state is not None
    target = _first_unit(state, player_id="player-b")
    _set_unit_starting_wounds(state, target.unit_instance_id, wounds=10)
    if mode is SecondaryMissionCardMode.FIXED:
        state.record_secondary_mission_card_state(
            SecondaryMissionCardState.active_fixed(
                player_id="player-a",
                secondary_mission_id="bring-it-down",
            )
        )
    else:
        state.record_secondary_mission_card_state(
            SecondaryMissionCardState.active_tactical(
                player_id="player-a",
                secondary_mission_id="bring-it-down",
                battle_round=3,
                source_result_id="evidence-swap-dual-mode-draw",
            )
        )
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=target.unit_instance_id,
        source_id="evidence-swap-dual-mode-destroyed",
        event_log=lifecycle.decision_controller.event_log,
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=mode,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    return lifecycle


def _two_round_bring_it_down_lifecycle() -> GameLifecycle:
    lifecycle = _two_defender_battlefield_dominance_lifecycle(
        phase=BattlePhase.FIGHT,
        battle_round=2,
    )
    state = lifecycle.state
    assert state is not None
    targets = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    assert len(targets) == 2
    for target in targets:
        _set_unit_starting_wounds(state, target.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    for battle_round, target in zip((2, 3), targets, strict=True):
        state.battle_round = battle_round
        state.active_player_id = "player-a"
        record_secondary_destruction_for_fixture(
            state,
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target.unit_instance_id,
            source_id=f"evidence-swap-round-{battle_round}-destroyed",
            event_log=lifecycle.decision_controller.event_log,
        )
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    return lifecycle


def _defend_stronghold_ready_lifecycle() -> tuple[GameLifecycle, GameState]:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=2)
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.ATTACKER_HOME)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.DEFENDER_HOME)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="p2-defend-stronghold-ready",
        )
    )
    return lifecycle, state


def _scored_reconnaissance_turn_end_lifecycle() -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="take-and-hold",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=1,
    )
    decisions = DecisionController()
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    _emit_oc_event(decisions=decisions, record=record)
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    return GameLifecycle(state=state, decision_controller=decisions)


def _scored_determined_acquisition_command_lifecycle() -> GameLifecycle:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="disruption",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=2,
    )
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.DEFENDER_HOME)
    decisions = DecisionController()
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=decisions, record=record)
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    return GameLifecycle(state=state, decision_controller=decisions)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "BattlePhase", "DecisionController", "GameConfig", "GameLifecycle"]
__all__ += ["GameLifecycleStage", "GameState", "ObjectiveControlTiming", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED", "Pose"]
__all__ += ["SecondaryMissionCardMode", "SecondaryMissionCardState", "SecondaryMissionMode"]
__all__ += ["UnitPlacement", "_add_unit_keyword", "_battlefield_dominance_lifecycle"]
__all__ += ["_bring_it_down_player_a_scored_lifecycle", "_defend_stronghold_ready_lifecycle"]
__all__ += ["_destroy_first_model", "_destroy_unit_with_events", "_emit_oc_event", "_first_unit"]
__all__ += ["_pending_command_boundary_lifecycle", "_pending_final_turn_end_boundary_lifecycle"]
__all__ += ["_place_player_on_role", "_place_unit_interior_non_overlapping"]
__all__ += ["_queue_pending_window", "_return_destroyed_unit"]
__all__ += ["_same_boundary_bring_it_down_and_assassination_lifecycle"]
__all__ += ["_same_boundary_two_player_bring_it_down_lifecycle"]
__all__ += ["_scored_command_boundary_after_mutation"]
__all__ += ["_scored_determined_acquisition_command_lifecycle"]
__all__ += ["_scored_reconnaissance_turn_end_lifecycle", "_set_unit_starting_wounds"]
__all__ += ["_single_mode_bring_it_down_lifecycle"]
__all__ += ["_two_defender_battlefield_dominance_lifecycle"]
__all__ += ["_two_model_battlefield_dominance_lifecycle"]
__all__ += ["_two_player_bring_it_down_scored_lifecycle", "_two_round_bring_it_down_lifecycle"]
__all__ += ["append_authenticated_normal_move", "army_muster_request"]
__all__ += ["complete_setup_through_gate", "create_deterministic_battlefield_scenario"]
__all__ += ["default_unit_selection", "mustered_armies", "phase11c_mission_setup"]
__all__ += ["phase17n_event_setup", "phase17n_state_with_setup"]
__all__ += ["record_secondary_destruction_for_fixture", "replace", "ruleset"]
__all__ += ["score_primary_objective_control_boundary", "secondary_choice"]
