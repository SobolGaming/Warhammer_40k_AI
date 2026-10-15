from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase9b_lifecycle import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    DEFAULT_MAX_LIFECYCLE_TRANSITIONS,
    SECONDARY_MISSION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    STRATAGEM_DECISION_TYPE,
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BattlePhase,
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    BattleRoundFlow,
    ChargePhaseState,
    ChargeRollRequest,
    ChargeRollResult,
    ChargingUnitSelection,
    CommandPhaseHandler,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    DiceRollManager,
    FightPhaseState,
    FightsFirstRegistry,
    GameConfig,
    GameConfigPayload,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    GameStatePayload,
    GeometrySourceKind,
    HeightSourceKind,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
    ModelProfileSelection,
    MovementPhaseState,
    ObjectiveControlTiming,
    PlaceholderPhaseHandler,
    RulesetDescriptor,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupCompletionGate,
    SetupSequenceDescriptor,
    SetupStep,
    SetupStepKind,
    ShootingPhaseState,
    UnitMusterSelection,
    WargearSelection,
    _advance_to_battle,
    _advance_to_secondary_mission_step,
    _army_muster_request,
    _army_muster_requests,
    _battle_flow,
    _battle_lifecycle_for_consistency,
    _battle_state,
    _choose_secondaries,
    _complete_setup_through_gate,
    _config,
    _decline_stratagem_window_if_pending,
    _descriptor_with_sequences,
    _lifecycle_is_in_battle,
    _mission_setup,
    _pending_request,
    _phase_state_consistency_payload,
    _public_secondary_choices,
    _request_payload,
    _start_lifecycle,
    _state,
    _state_battle_phase,
    _submit_pending,
    accepted_model_geometry,
    chapter_approved_2026_27_mission_pack,
    create_deterministic_battlefield_scenario,
    drain_pending_secondary_mission_setup,
    ensure_army_mustered_events_for_fixture,
    game_lifecycle_stage_from_token,
    inspect,
    json,
    lifecycle_status_kind_from_token,
    muster_army,
    pytest,
    replace,
    seed_completed_fight_phase,
    submit_all_deployments_if_pending,
)


def test_setup_steps_advance_in_ruleset_descriptor_order() -> None:
    lifecycle = _start_lifecycle()
    assert lifecycle.state is not None
    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    _submit_pending(lifecycle, option_id="tactical", result_number=1)
    status = _submit_pending(
        lifecycle,
        option_id="fixed:assassination:bring_it_down",
        result_number=2,
    )
    submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix="phase9b-setup-order-deploy",
    )

    observed_steps = [
        event.payload["step"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "setup_step_completed" and isinstance(event.payload, dict)
    ]

    assert observed_steps == [
        step.value for step in RulesetDescriptor.warhammer_40000_eleventh().setup_sequence.steps
    ]


def test_lifecycle_mustering_uses_game_config_reviewed_model_geometry() -> None:
    geometry = accepted_model_geometry()
    lifecycle = _start_lifecycle(_config(model_geometries=(geometry,)))

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    for army in lifecycle.state.army_definitions:
        model_geometry = army.units[0].own_models[0].geometry
        assert model_geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
        assert model_geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
        assert model_geometry.height_inches == 1.55
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.config.model_geometries == (geometry,)
    assert restored.to_payload() == lifecycle.to_payload()


def test_lifecycle_mustering_preserves_partial_reviewed_model_geometry() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    reviewed_geometry = accepted_model_geometry()
    player_a_request = _army_muster_request(
        catalog=catalog,
        player_id="player-a",
        army_id="army-alpha",
        unit_selection_id="intercessor-unit-1",
    )
    player_b_request = replace(
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selection_id="boyz-unit-1",
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="boyz-unit-1",
                datasheet_id="core-boyz-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
                wargear_selections=(),
            ),
        ),
    )
    config = _config(
        army_catalog=catalog,
        army_muster_requests=(player_a_request, player_b_request),
        model_geometries=(reviewed_geometry,),
    )
    lifecycle = _start_lifecycle(config)

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    armies_by_player_id = {army.player_id: army for army in lifecycle.state.army_definitions}
    accepted_model = armies_by_player_id["player-a"].units[0].own_models[0]
    unresolved_model = armies_by_player_id["player-b"].units[0].own_models[0]
    assert accepted_model.geometry.geometry_source_kind is (
        GeometrySourceKind.CATALOG_GEOMETRY_RECORD
    )
    assert accepted_model.geometry.height_source_kind is (HeightSourceKind.CATALOG_GEOMETRY_RECORD)
    assert unresolved_model.geometry.geometry_source_kind is GeometrySourceKind.CATALOG_BASE_SIZE
    assert unresolved_model.geometry.height_source_kind is HeightSourceKind.KEYWORD_HEURISTIC
    assert GameConfig.from_payload(config.to_payload()).model_geometries == (reviewed_geometry,)


def test_game_config_rejects_model_geometry_for_unknown_catalog_profile() -> None:
    with pytest.raises(GameLifecycleError, match="unknown catalog model profile"):
        _config(model_geometries=(accepted_model_geometry("unknown-model-profile"),))


def test_game_config_rejects_duplicate_model_geometry_profiles() -> None:
    geometry = accepted_model_geometry()

    with pytest.raises(GameLifecycleError, match="unique by model_profile_id"):
        _config(model_geometries=(geometry, geometry))


def test_game_config_payload_rejects_structurally_incomplete_model_geometry() -> None:
    payload = cast(
        GameConfigPayload,
        json.loads(
            json.dumps(
                _config(model_geometries=(accepted_model_geometry(),)).to_payload(),
                sort_keys=True,
            )
        ),
    )
    assert "model_geometries" in payload
    geometry_payload = cast(
        dict[str, object],
        cast(object, payload["model_geometries"][0]),
    )
    del geometry_payload["support_base"]

    with pytest.raises(GameLifecycleError, match="model_geometries payload is invalid"):
        GameConfig.from_payload(payload)


def test_game_config_payload_rejects_non_record_model_geometry() -> None:
    payload = _config().to_payload()
    payload["model_geometries"] = cast(list[ModelGeometryCatalogRecordPayload], [1])

    with pytest.raises(GameLifecycleError, match="model_geometries payload is invalid"):
        GameConfig.from_payload(payload)


def test_lifecycle_replay_payload_preserves_mustered_army_definitions() -> None:
    lifecycle = _start_lifecycle()
    lifecycle.advance_until_decision_or_terminal()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert len(payload["state"]["army_definitions"]) == 2
    assert "army-alpha:intercessor-unit-1" in blob
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_lifecycle_muster_armies_fails_before_setup_advancement_on_invalid_request() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bad_wargear = WargearSelection(
        option_id="core-intercessor-like-infantry:default-wargear",
        model_profile_id="core-intercessor-like",
        wargear_ids=("core-heavy-cannon",),
    )
    config = _config(
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
                wargear_selections=(bad_wargear,),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )
    lifecycle = _start_lifecycle(config)

    with pytest.raises(GameLifecycleError, match="MUSTER_ARMIES"):
        lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.MUSTER_ARMIES
    assert lifecycle.state.army_definitions == []


def test_setup_completion_enters_battle_round_one_command_phase() -> None:
    lifecycle = _start_lifecycle()

    _advance_to_battle(lifecycle)

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battle_round == 1
    assert lifecycle.state.active_player_id == "player-a"
    assert lifecycle.state.current_battle_phase is BattlePhase.COMMAND


def test_battle_phases_advance_command_movement_shooting_charge_fight() -> None:
    state = _battle_state()
    flow = _battle_flow()

    assert _state_battle_phase(state) is BattlePhase.COMMAND
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.MOVEMENT
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.SHOOTING
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.CHARGE
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.FIGHT


def test_lifecycle_reads_battle_phase_order_from_ruleset_descriptor() -> None:
    descriptor = _descriptor_with_sequences(
        battle_phases=(
            BattlePhaseKind.COMMAND,
            BattlePhaseKind.SHOOTING,
            BattlePhaseKind.MOVEMENT,
            BattlePhaseKind.CHARGE,
            BattlePhaseKind.FIGHT,
        )
    )
    state = _battle_state(_config(ruleset_descriptor=descriptor))
    _battle_flow().advance(state=state, decisions=GameLifecycle().decision_controller)

    assert state.current_battle_phase is BattlePhase.SHOOTING


def test_placeholder_phase_handler_emits_explicit_noop_and_advances_boundary() -> None:
    state = _battle_state()
    flow = _battle_flow()
    decisions = GameLifecycle().decision_controller
    flow.advance(state=state, decisions=decisions)

    status = flow.advance(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert status.payload == {
        "completed_phase": BattlePhase.MOVEMENT.value,
        "phase_body_status": "placeholder_noop",
        "battle_round": 1,
        "active_player_id": "player-a",
        "current_phase": BattlePhase.SHOOTING.value,
    }
    assert tuple(event.event_type for event in decisions.event_log.records) == (
        "timing_window_opened",
        "timing_window_resolved",
        "timing_window_opened",
        "timing_window_resolved",
        "timing_window_opened",
        "command_phase_start_rules_discovered",
        "timing_window_resolved",
        "command_phase_start_synchronous_hooks_completed",
        "command_phase_start_effect_pass_completed",
        "command_phase_start_boundary_completed",
        "command_points_gained",
        "command_points_gained",
        "command_step_started",
        "command_phase_scoring_hooks_resolved",
        "battle_shock_step_snapshot_created",
        "battle_shock_step_completed",
        "timing_window_opened",
        "timing_window_resolved",
        "end_boundary_objective_control_determined",
        "timing_window_opened",
        "timing_window_resolved",
        "primary_scoring_commit_checkpoint_recorded",
        "battle_phase_completed",
        "timing_window_opened",
        "timing_window_resolved",
        "phase_body_placeholder_noop",
        "end_boundary_objective_control_determined",
        "timing_window_opened",
        "timing_window_resolved",
        "battle_phase_completed",
    )

    body_events = decisions.event_log.records[16:18]
    for event in body_events:
        payload = event.payload
        assert isinstance(payload, dict)
        window = payload["timing_window"]
        assert isinstance(window, dict)
        descriptor = window["descriptor"]
        assert isinstance(descriptor, dict)
        assert descriptor["source_step"] == "command_abilities"
        assert descriptor["source_rule_id"] == "rule:08:08.04:1"


def test_turn_end_objective_control_audit_follows_post_cleanup_capture() -> None:
    state = _battle_state()
    flow = _battle_flow()
    decisions = DecisionController()

    for _ in range(5):
        if state.current_battle_phase is BattlePhase.FIGHT:
            seed_completed_fight_phase(state)
        flow.advance(state=state, decisions=decisions)

    fight_boundary_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload.get("phase") == BattlePhase.FIGHT.value
    )
    assert len(fight_boundary_events) == 2
    phase_end_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.PHASE_END
    )
    turn_end_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )
    fight_boundary_payloads = tuple(
        cast(dict[str, JsonValue], event.payload) for event in fight_boundary_events
    )
    assert [payload["record_ids"] for payload in fight_boundary_payloads] == [
        [phase_end_record.record_id],
        [turn_end_record.record_id],
    ]
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    turn_end_audit_index = decisions.event_log.records.index(fight_boundary_events[-1])
    phase_completed_index = next(
        index
        for index in range(turn_end_audit_index + 1, len(event_types))
        if event_types[index] == "battle_phase_completed"
    )
    turn_start_evidence_indexes = tuple(
        index
        for index in range(turn_end_audit_index + 1, len(event_types))
        if event_types[index] == "primary_turn_start_evidence_recorded"
    )
    assert turn_end_audit_index < phase_completed_index
    assert all(
        turn_end_audit_index < index < phase_completed_index
        for index in turn_start_evidence_indexes
    )


def test_battle_round_increments_after_all_players_complete_fight_phase() -> None:
    state = _battle_state()
    flow = _battle_flow()

    for _ in range(10):
        if state.current_battle_phase is BattlePhase.FIGHT:
            seed_completed_fight_phase(state)
        flow.advance(state=state, decisions=GameLifecycle().decision_controller)

    assert state.battle_round == 2
    assert state.active_player_id == "player-a"
    assert state.current_battle_phase is BattlePhase.COMMAND


def test_advance_until_reaches_first_decision_from_initial_state_in_one_call() -> None:
    lifecycle = _start_lifecycle()

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert status.decision_request.actor_id == "player-a"
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_tactical_secondary_draws_occur_in_command_phase_not_setup() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:assassination:bring_it_down",
    )
    setup_decision_types = [
        record.request.decision_type for record in lifecycle.decision_controller.records
    ]

    status = lifecycle.advance_until_decision_or_terminal()
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = submit_all_deployments_if_pending(
            lifecycle,
            status,
            result_id_prefix="phase9b-tactical-setup-deploy",
        )
        if _lifecycle_is_in_battle(lifecycle):
            break
        status = lifecycle.advance_until_decision_or_terminal()

    status = lifecycle.advance_until_decision_or_terminal()

    assert setup_decision_types == [
        SECONDARY_MISSION_DECISION_TYPE,
        SECONDARY_MISSION_DECISION_TYPE,
    ]
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    assert status.decision_request.actor_id == "player-a"
    assert _request_payload(status.decision_request)["phase"] == BattlePhase.COMMAND.value


def test_tactical_secondary_draw_decision_records_command_draw_and_enters_movement() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:assassination:bring_it_down",
    )
    status = lifecycle.advance_until_decision_or_terminal()
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = submit_all_deployments_if_pending(
            lifecycle,
            status,
            result_id_prefix="phase9b-tactical-draw-deploy",
        )
        if _lifecycle_is_in_battle(lifecycle):
            break
        status = lifecycle.advance_until_decision_or_terminal()

    status = lifecycle.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    draw_result = DecisionResult.for_request(
        result_id="decision-result-000003",
        request=status.decision_request,
        selected_option_id="draw",
    )
    follow_up_status = lifecycle.submit_decision(draw_result)
    follow_up_status = _decline_stratagem_window_if_pending(
        lifecycle,
        follow_up_status,
        result_number=4,
    )

    assert lifecycle.state is not None
    assert follow_up_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert follow_up_status.decision_request is not None
    assert follow_up_status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert follow_up_status.decision_request.actor_id == "player-a"
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert lifecycle.state.battlefield_state is not None
    assert len(lifecycle.state.tactical_secondary_draws) == 1
    draw = lifecycle.state.tactical_secondary_draws[0]
    assert draw.player_id == "player-a"
    assert draw.battle_round == 1
    assert draw.draw_count == 2
    assert len(lifecycle.decision_controller.queue.pending_requests) == 1
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "charge_phase_state requires CHARGE phase"),
        ("active_player_drift", "charge_phase_state active player drift"),
        ("battle_round_drift", "charge_phase_state battle round drift"),
        ("selected_enemy", "selected unit is not active player's unit"),
        ("roll_unit_not_selected", "roll unit was not selected"),
        ("unknown_target", "target unit is unknown"),
        ("friendly_target", "target unit is not an enemy"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_charge_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.CHARGE
    )
    state_payload = payload["state"]
    charge_payload = cast(dict[str, object], state_payload["charge_phase_state"])
    selection = cast(dict[str, object], charge_payload["active_selection"])
    distance_states = cast(list[dict[str, object]], charge_payload["distance_states"])
    roll_result = cast(dict[str, object], distance_states[0]["roll_result"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.MOVEMENT.value
        )
    elif corruption == "active_player_drift":
        charge_payload["active_player_id"] = "player-b"
        selection["player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        charge_payload["battle_round"] = 2
        selection["battle_round"] = 2
    elif corruption == "selected_enemy":
        charge_payload["selected_unit_ids"] = [alpha_unit_id, beta_unit_id]
    elif corruption == "roll_unit_not_selected":
        charge_payload["selected_unit_ids"] = []
        charge_payload["active_selection"] = None
    elif corruption == "unknown_target":
        roll_result["reachable_target_distances_inches"] = {"unknown-target": 3.0}
    elif corruption == "friendly_target":
        roll_result["reachable_target_distances_inches"] = {alpha_unit_id: 3.0}

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "movement_phase_state requires MOVEMENT phase"),
        ("active_player_drift", "movement_phase_state active player drift"),
        ("battle_round_drift", "movement_phase_state battle round drift"),
        ("selected_enemy", "selected unit is not active player's unit"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_movement_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, _alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.MOVEMENT
    )
    state_payload = payload["state"]
    movement_payload = cast(dict[str, object], state_payload["movement_phase_state"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.SHOOTING.value
        )
    elif corruption == "active_player_drift":
        movement_payload["active_player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        movement_payload["battle_round"] = 2
    elif corruption == "selected_enemy":
        movement_payload["selected_unit_ids"] = [beta_unit_id]
        movement_payload["moved_unit_ids"] = [beta_unit_id]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "shooting_phase_state requires SHOOTING phase"),
        ("active_player_drift", "shooting_phase_state active player drift"),
        ("battle_round_drift", "shooting_phase_state battle round drift"),
        ("selected_enemy", "selected unit is not active player's unit"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_shooting_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, _alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.SHOOTING
    )
    state_payload = payload["state"]
    shooting_payload = cast(dict[str, object], state_payload["shooting_phase_state"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.MOVEMENT.value
        )
    elif corruption == "active_player_drift":
        shooting_payload["active_player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        shooting_payload["battle_round"] = 2
    elif corruption == "selected_enemy":
        shooting_payload["selected_unit_ids"] = [beta_unit_id]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "fight_phase_state requires FIGHT phase"),
        ("active_player_drift", "fight_phase_state active player drift"),
        ("battle_round_drift", "fight_phase_state battle round drift"),
        ("next_player_unknown", "next player is not in this game"),
        ("unit_unknown", "fight_phase_state unit is unknown"),
        ("passed_player_unknown", "passed player is not in this game"),
        ("activation_unit_unknown", "activation unit is unknown"),
        ("activation_player_drift", "activation player drift"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_fight_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, alpha_unit_id, _beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.FIGHT
    )
    state_payload = payload["state"]
    fight_payload = cast(dict[str, object], state_payload["fight_phase_state"])
    fight_order = cast(dict[str, object], fight_payload["fight_order_state"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.CHARGE.value
        )
    elif corruption == "active_player_drift":
        fight_payload["active_player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        fight_payload["battle_round"] = 2
    elif corruption == "next_player_unknown":
        fight_order["next_player_id"] = "player-c"
    elif corruption == "unit_unknown":
        fight_order["engaged_at_fight_step_start_unit_ids"] = ["unknown-fight-unit"]
    elif corruption == "passed_player_unknown":
        fight_order["passed_player_ids"] = ["player-c"]
    elif corruption in {"activation_unit_unknown", "activation_player_drift"}:
        fight_order["activation_selections"] = [
            {
                "player_id": (
                    "player-b" if corruption == "activation_player_drift" else "player-a"
                ),
                "battle_round": 1,
                "unit_instance_id": (
                    alpha_unit_id
                    if corruption == "activation_player_drift"
                    else "unknown-fight-unit"
                ),
                "ordering_band": "remaining_combats",
                "fight_type": "normal",
                "eligibility_reasons": ["currently_engaged"],
                "request_id": "phase9b-fight-activation-request",
                "result_id": "phase9b-fight-activation-result",
                "interrupt_id": None,
            }
        ]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("selection_missing_history", "selection is missing from selected history"),
        ("active_missing_selection", "must match exactly one selection"),
        ("active_selection_drift", "Active Fight activation selection drift"),
        ("duplicate_result_id", "selection result IDs must be unique"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_fight_activation_history(
    corruption: str,
    expected_message: str,
) -> None:
    payload, alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(phase=BattlePhase.FIGHT)
    fight_payload = cast(dict[str, object], payload["state"]["fight_phase_state"])
    fight_order = cast(dict[str, object], fight_payload["fight_order_state"])
    selection = {
        "player_id": "player-a",
        "battle_round": 1,
        "unit_instance_id": alpha_unit_id,
        "ordering_band": "remaining_combats",
        "fight_type": "normal",
        "eligibility_reasons": ["currently_engaged"],
        "request_id": "phase9b-fight-history-request",
        "result_id": "phase9b-fight-history-result",
        "interrupt_id": None,
    }
    if corruption == "selection_missing_history":
        fight_order["activation_selections"] = [selection]
    elif corruption == "active_missing_selection":
        fight_payload["active_activation"] = selection
    elif corruption == "active_selection_drift":
        fight_order["selected_to_fight_unit_ids"] = [alpha_unit_id]
        fight_order["activation_selections"] = [selection]
        fight_payload["active_activation"] = {
            **selection,
            "request_id": "phase9b-fight-history-drift",
        }
    elif corruption == "duplicate_result_id":
        fight_order["selected_to_fight_unit_ids"] = [alpha_unit_id, beta_unit_id]
        fight_order["activation_selections"] = [
            selection,
            {
                **selection,
                "player_id": "player-b",
                "unit_instance_id": beta_unit_id,
                "request_id": "phase9b-fight-history-request-beta",
            },
        ]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


def test_no_ui_or_headless_specific_phase_path_exists() -> None:
    public_methods = {
        name
        for name, _member in inspect.getmembers(GameLifecycle, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == {
        "advance_until_decision_or_terminal",
        "pending_decision_request",
        "start",
        "submit_decision",
        "to_payload",
    }
    assert callable(GameLifecycle.from_payload)


__all__: list[str] = []
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "BattlePhaseSequenceDescriptor"]
__all__ += ["BattleRoundFlow", "ChargePhaseState", "ChargeRollRequest", "ChargeRollResult"]
__all__ += ["DECLINE_STRATAGEM_WINDOW_OPTION_ID", "ChargingUnitSelection", "CommandPhaseHandler"]
__all__ += ["DEFAULT_MAX_LIFECYCLE_TRANSITIONS", "DecisionOption", "DecisionRequest"]
__all__ += ["DetachmentSelection", "DiceRollManager", "FightPhaseState", "FightsFirstRegistry"]
__all__ += ["GameState", "GameStatePayload", "LifecycleStatus", "MissionSetup"]
__all__ += ["ModelGeometryCatalogRecord", "MovementPhaseState", "PlaceholderPhaseHandler"]
__all__ += ["STRATAGEM_DECISION_TYPE", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["SetupCompletionGate", "SetupSequenceDescriptor", "SetupStepKind"]
__all__ += ["ShootingPhaseState", "_advance_to_secondary_mission_step", "_army_muster_requests"]
__all__ += ["_battle_lifecycle_for_consistency", "_complete_setup_through_gate", "_mission_setup"]
__all__ += ["_pending_request", "_public_secondary_choices", "_state"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["drain_pending_secondary_mission_setup", "ensure_army_mustered_events_for_fixture"]
__all__ += ["game_lifecycle_stage_from_token", "lifecycle_status_kind_from_token", "muster_army"]
