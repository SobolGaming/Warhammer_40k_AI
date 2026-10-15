from __future__ import annotations

from tests.shared.category_migration.phase17n_step6g_secondary_certification import (
    _LAYOUT_ROW,
    _LIFECYCLE_CERTIFICATION_ROWS,
    _SCORING_PLAYER_IDS,
    SECONDARY_CARD_MODE_CERTIFICATION_COUNT,
    SECONDARY_LIFECYCLE_CERTIFICATION_COUNT,
    SECONDARY_MISSION_COUNT,
    SELECT_BEACON_UNIT_DECISION_TYPE,
    SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
    SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
    STEP6G_MISSION_PARTITIONS,
    TURN_CAP_TACTICAL_IDS,
    ArmyDefinition,
    AttachmentDeclaration,
    BattlePhase,
    DecisionController,
    DecisionError,
    DecisionResult,
    FiniteOptionSubmission,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    LifecycleStatusKind,
    LocalGameSession,
    ModelPlacement,
    ObjectiveControlTiming,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerRole,
    Pose,
    PrimaryUnattributedDestructionCause,
    ReserveKind,
    ReserveState,
    RulesUnitPresence,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SecondaryMissionSelection,
    UnitInstance,
    _attached_burden_state,
    _command_tactical_state,
    _configured_step6g_lifecycle,
    _decisions_for_seeded_secondary_state,
    _first_intercessor,
    _home_objective,
    _lifecycle_row,
    _place_unit,
    _record_unresolved_tactical,
    _restore_unit_wounds,
    _score_certified_row_from_state,
    _secondary_transactions,
    _seed_completed_fight_phase,
    _seed_single_tactical_card,
    _setup_for_layout,
    _tactical_fight_state,
    _turn_cap_state,
    _unit_by_id,
    _unit_for,
    _zero_and_remove_unit,
    apply_tactical_secondary_when_drawn,
    army_muster_request,
    attached_when_drawn_state,
    certification_unit_selections,
    complete_setup_through_gate,
    create_deterministic_battlefield_scenario,
    deepcopy,
    default_unit_selection,
    mustered_armies,
    next_secondary_mission_choice_request,
    next_tactical_secondary_when_drawn_request,
    phase11c_config,
    phase17n_state_with_setup,
    pytest,
    record_existing_primary_turn_start_evidence_events_for_fixture,
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
    record_primary_turn_start_evidence_for_fixture,
    record_secondary_destruction_for_fixture,
    record_unresolved_when_drawn_card,
    replace,
    reposition_destruction_policy,
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
    resolved_secondary_mission_selection_for_card,
    score_turn_end_mission_scoring_boundary,
    secondary_mission_inventory_rows,
    secondary_mission_selection_for_card,
    seed_sequential_tactical_turn_cap_conditions,
    step6g_matrix_case_keys,
    unit_selection,
    validate_attached_rules_unit_identity_after_destruction,
)


def test_phase17n_step6g_inventory_covers_every_secondary_card_and_mode() -> None:
    rows = secondary_mission_inventory_rows()
    assert len(rows) == SECONDARY_MISSION_COUNT
    assert sum(len(row.modes) for row in rows) == SECONDARY_CARD_MODE_CERTIFICATION_COUNT
    assert all(row.state_backed for row in rows)
    assert {row.secondary_mission_id for row in rows} == {
        "a-grievous-blow",
        "a-tempting-target",
        "assassination",
        "beacon",
        "behind-enemy-lines",
        "bring-it-down",
        "burden-of-trust",
        "centre-ground",
        "cleanse",
        "defend-stronghold",
        "display-of-might",
        "engage-on-all-fronts",
        "forward-position",
        "no-prisoners",
        "outflank",
        "overwhelming-force",
        "plunder",
        "secure-no-mans-land",
    }
    assert len(_LIFECYCLE_CERTIFICATION_ROWS) == SECONDARY_LIFECYCLE_CERTIFICATION_COUNT
    assert {row.layout_id for row in _LIFECYCLE_CERTIFICATION_ROWS} == {_LAYOUT_ROW.layout_id}
    assert {row.scoring_player_id for row in _LIFECYCLE_CERTIFICATION_ROWS} == set(
        _SCORING_PLAYER_IDS
    )
    for partition_index, partition in enumerate(STEP6G_MISSION_PARTITIONS):
        assert all(
            partition.isdisjoint(other_partition)
            for other_partition in STEP6G_MISSION_PARTITIONS[partition_index + 1 :]
        )
    assert frozenset().union(*STEP6G_MISSION_PARTITIONS) == {
        row.secondary_mission_id for row in rows
    }
    partition_case_keys = tuple(
        step6g_matrix_case_keys(partition) for partition in STEP6G_MISSION_PARTITIONS
    )
    for partition_index, partition_keys in enumerate(partition_case_keys):
        assert all(
            partition_keys.isdisjoint(other_partition_keys)
            for other_partition_keys in partition_case_keys[partition_index + 1 :]
        )
    expected_case_keys = {
        (row.secondary_mission_id, row.mode, row.scoring_player_id, outcome)
        for row in _LIFECYCLE_CERTIFICATION_ROWS
        for outcome in (("score", "retain") if row.mode == "tactical" else ("score",))
    }
    assert frozenset().union(*partition_case_keys) == expected_case_keys
    assert len(expected_case_keys) == 80


@pytest.mark.parametrize(
    ("secondary_mission_id", "decision_type", "event_type"),
    [
        (
            "a-tempting-target",
            SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
            "tempting_target_objective_selected",
        ),
        ("beacon", SELECT_BEACON_UNIT_DECISION_TYPE, "beacon_unit_selected"),
        (
            "burden-of-trust",
            SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
            "burden_of_trust_guard_selected",
        ),
    ],
)
def test_phase17n_step6g_secondary_selection_uses_adapter_decision_path(
    secondary_mission_id: str,
    decision_type: str,
    event_type: str,
) -> None:
    state = phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=2,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )
    state.secondary_mission_choices = [
        choice for choice in state.secondary_mission_choices if choice.player_id != "player-a"
    ]
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-choice-{secondary_mission_id}",
        )
    )
    lifecycle = _configured_step6g_lifecycle(
        state=state,
        decisions=DecisionController(),
    )
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None

    waiting = next_secondary_mission_choice_request(
        state=lifecycle_state,
        decisions=lifecycle.decision_controller,
    )

    assert waiting is not None
    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == decision_type
    assert request.actor_id == (
        "player-b"
        if decision_type == SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE
        else "player-a"
    )
    option = (
        next(candidate for candidate in request.options if candidate.option_id.startswith("guard:"))
        if decision_type == SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE
        else request.options[0]
    )
    status = LocalGameSession(lifecycle=lifecycle).submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id=f"phase17n-choice-result-{secondary_mission_id}",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    updated = lifecycle_state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert updated is not None
    selection = secondary_mission_selection_for_card(updated)
    assert selection is not None
    if secondary_mission_id == "a-tempting-target":
        assert selection.tempting_objective_id == option.option_id.removeprefix("tempting:")
    elif secondary_mission_id == "beacon":
        assert selection.beacon_unit_instance_id == option.option_id.removeprefix("beacon:")
    else:
        objective_id, unit_id = option.option_id.removeprefix("guard:").split(":", maxsplit=1)
        assert selection.resolved_guard_objective_ids == (objective_id,)
        assert selection.guarded_objective_unit_ids == ((objective_id, unit_id),)
    assert any(
        event.event_type == event_type for event in lifecycle.decision_controller.event_log.records
    )
    restored = GameLifecycle.from_payload(deepcopy(lifecycle.to_payload()))
    assert restored.to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize(
    "card_player_id",
    ["player-a", "player-b"],
    ids=("attacker-owns-card", "defender-owns-card"),
)
def test_a_grievous_blow_when_drawn_sees_enemy_attached_unit(
    card_player_id: str,
) -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id=card_player_id,
        bodyguard_model_count=12,
        secondary_mission_id="a-grievous-blow",
    )
    enemy_army = next(army for army in state.army_definitions if army.player_id != card_player_id)
    formation = enemy_army.attached_units[0]
    assert len(enemy_army.unit_by_id(formation.bodyguard_unit_instance_id).own_models) == 12
    assert len(enemy_army.unit_by_id(formation.leader_unit_instance_ids[0]).own_models) == 1
    assert (
        state.starting_strength_record_for_unit(
            formation.attached_unit_instance_id
        ).starting_model_count
        == 13
    )

    assert (
        next_tactical_secondary_when_drawn_request(
            state=state,
            decisions=DecisionController(),
        )
        is None
    )


@pytest.mark.parametrize("presence", ["reserves", "embarked"])
def test_a_grievous_blow_when_drawn_excludes_off_battlefield_attached_units(
    presence: RulesUnitPresence,
) -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=12,
        secondary_mission_id="a-grievous-blow",
        presence=presence,
    )
    status = next_tactical_secondary_when_drawn_request(
        state=state,
        decisions=DecisionController(),
    )
    assert status is not None
    assert status.decision_request is not None
    assert "discard:a-grievous-blow" in {
        option.option_id for option in status.decision_request.options
    }


@pytest.mark.parametrize(
    ("bodyguard_model_count", "discard_available"),
    [(11, True), (12, False)],
)
def test_a_grievous_blow_when_drawn_retains_original_attached_starting_strength(
    bodyguard_model_count: int,
    discard_available: bool,
) -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=bodyguard_model_count,
        secondary_mission_id="a-grievous-blow",
        record_card=False,
    )
    formation = state.army_definitions[1].attached_units[0]
    leader_id = formation.leader_unit_instance_ids[0]
    _zero_and_remove_unit(state, leader_id)
    validate_attached_rules_unit_identity_after_destruction(
        state=state,
        rules_unit_instance_id=formation.attached_unit_instance_id,
    )
    assert (
        state.starting_strength_record_for_unit(
            formation.attached_unit_instance_id
        ).starting_model_count
        == bodyguard_model_count + 1
    )
    record_unresolved_when_drawn_card(
        state,
        player_id="player-a",
        secondary_mission_id="a-grievous-blow",
    )

    status = next_tactical_secondary_when_drawn_request(
        state=state,
        decisions=DecisionController(),
    )
    if discard_available:
        assert status is not None
        assert status.decision_request is not None
        assert "discard:a-grievous-blow" in {
            option.option_id for option in status.decision_request.options
        }
    else:
        assert status is None


def test_bring_it_down_when_drawn_sees_w10_model_inside_attached_unit() -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=5,
        secondary_mission_id="bring-it-down",
        leader_starting_wounds=10,
    )
    enemy_army = state.army_definitions[1]
    formation = enemy_army.attached_units[0]
    leader = enemy_army.unit_by_id(formation.leader_unit_instance_ids[0])
    assert leader.own_models[0].initial_wounds == 10
    assert (
        next_tactical_secondary_when_drawn_request(
            state=state,
            decisions=DecisionController(),
        )
        is None
    )


def test_burden_of_trust_still_scores_after_bodyguard_destruction() -> None:
    state = _attached_burden_state()
    formation = state.army_definitions[0].attached_units[0]
    attached_id = formation.attached_unit_instance_id
    bodyguard_id = formation.bodyguard_unit_instance_id
    leader_id = formation.leader_unit_instance_ids[0]
    home = _home_objective(state, player_id="player-a")
    _place_unit(state, bodyguard_id, home.x_inches, home.y_inches)
    _place_unit(state, leader_id, home.x_inches, home.y_inches)
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id="burden-of-trust",
        battle_round=state.battle_round,
        source_result_id="phase17n-burden-split",
    )
    assert state.mission_setup is not None
    state.record_secondary_mission_card_state(
        card.with_selection(
            SecondaryMissionSelection().with_guards(
                guarded_objective_unit_ids=((home.objective_marker_id, attached_id),),
                resolved_guard_objective_ids=tuple(
                    marker.objective_marker_id for marker in state.mission_setup.objective_markers
                ),
                battle_round=state.battle_round,
            )
        )
    )
    bodyguard = _unit_by_id(state, bodyguard_id)
    _zero_and_remove_unit(state, bodyguard.unit_instance_id)
    validate_attached_rules_unit_identity_after_destruction(
        state=state,
        rules_unit_instance_id=attached_id,
    )
    _place_unit(state, leader_id, home.x_inches, home.y_inches)
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="burden-of-trust",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    transactions = _secondary_transactions(
        state,
        player_id="player-a",
        source_id="burden-of-trust",
    )
    assert len(transactions) == 1
    assert transactions[0].amount == 2


__all__: list[str] = []
__all__ += ["ArmyDefinition", "AttachmentDeclaration", "DecisionError", "DecisionResult"]
__all__ += ["FiniteOptionSubmission", "GameLifecycleError", "GameLifecycleStage", "GameState"]
__all__ += ["ModelPlacement", "ObjectiveControlTiming", "ObjectiveMarkerDefinition"]
__all__ += ["ObjectiveMarkerRole", "Pose", "PrimaryUnattributedDestructionCause", "ReserveKind"]
__all__ += ["TURN_CAP_TACTICAL_IDS", "ReserveState", "SecondaryMissionCardStatus", "UnitInstance"]
__all__ += ["_command_tactical_state", "_decisions_for_seeded_secondary_state"]
__all__ += ["_first_intercessor", "_lifecycle_row", "_record_unresolved_tactical"]
__all__ += ["_restore_unit_wounds", "_score_certified_row_from_state"]
__all__ += ["_seed_completed_fight_phase", "_seed_single_tactical_card", "_tactical_fight_state"]
__all__ += ["_turn_cap_state", "_unit_for", "apply_tactical_secondary_when_drawn"]
__all__ += ["army_muster_request", "complete_setup_through_gate"]
__all__ += ["create_deterministic_battlefield_scenario", "default_unit_selection"]
__all__ += ["mustered_armies", "phase11c_config"]
__all__ += ["record_existing_primary_turn_start_evidence_events_for_fixture"]
__all__ += ["record_new_primary_battlefield_departure_events"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_secondary_destruction_for_fixture", "replace"]
__all__ += ["reposition_destruction_policy", "request_tactical_secondary_discard"]
__all__ += ["request_tactical_secondary_score", "resolved_secondary_mission_selection_for_card"]
__all__ += ["score_turn_end_mission_scoring_boundary"]
__all__ += ["seed_sequential_tactical_turn_cap_conditions", "unit_selection"]
