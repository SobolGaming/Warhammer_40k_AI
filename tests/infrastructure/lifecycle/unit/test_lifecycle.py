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


def test_game_state_replace_army_definitions_sorts_and_validates() -> None:
    config = _config()
    state = GameState.from_config(config)
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )

    state.replace_army_definitions([armies[1], armies[0]])

    assert [army.player_id for army in state.army_definitions] == ["player-a", "player-b"]
    with pytest.raises(GameLifecycleError, match="ArmyDefinition values"):
        state.replace_army_definitions(cast(list[ArmyDefinition], [object()]))


def test_game_state_phase_state_mutators_clear_validated_state_fields() -> None:
    state = GameState.from_config(_config())

    state.replace_command_step_state(None)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_out_of_phase_shooting_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)

    assert state.command_step_state is None
    assert state.movement_phase_state is None
    assert state.shooting_phase_state is None
    assert state.out_of_phase_shooting_state is None
    assert state.charge_phase_state is None
    assert state.fight_phase_state is None


def test_new_game_starts_at_muster_armies_and_records_descriptor_hash() -> None:
    config = _config()
    lifecycle = GameLifecycle()
    status = lifecycle.start(config)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.SETUP
    assert lifecycle.state.current_setup_step is SetupStep.MUSTER_ARMIES
    assert lifecycle.state.ruleset_descriptor_hash == config.ruleset_descriptor.descriptor_hash
    assert _state(lifecycle)["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash


def test_lifecycle_muster_armies_consumes_requests_and_records_runtime_armies() -> None:
    lifecycle = _start_lifecycle()

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS
    assert lifecycle.state.missing_army_player_ids() == ()
    assert tuple(army.player_id for army in lifecycle.state.army_definitions) == (
        "player-a",
        "player-b",
    )
    assert tuple(army.army_id for army in lifecycle.state.army_definitions) == (
        "army-alpha",
        "army-beta",
    )
    assert [
        event.payload["player_id"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "army_mustered" and isinstance(event.payload, dict)
    ] == ["player-a", "player-b"]


def test_game_config_model_geometries_round_trip_only_when_present() -> None:
    config_without_reviewed_geometry = _config()
    payload_without_reviewed_geometry = config_without_reviewed_geometry.to_payload()

    assert "model_geometries" not in payload_without_reviewed_geometry
    assert GameConfig.from_payload(payload_without_reviewed_geometry).model_geometries is None

    geometry = accepted_model_geometry()
    config_with_reviewed_geometry = _config(model_geometries=(geometry,))
    payload_with_reviewed_geometry = config_with_reviewed_geometry.to_payload()

    assert payload_with_reviewed_geometry.get("model_geometries") == [geometry.to_payload()]
    assert GameConfig.from_payload(payload_with_reviewed_geometry).to_payload() == (
        payload_with_reviewed_geometry
    )


def test_game_config_requires_muster_requests_for_every_player() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()

    with pytest.raises(GameLifecycleError, match="every player"):
        _config(
            army_catalog=catalog,
            army_muster_requests=(
                _army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selection_id="intercessor-unit-1",
                ),
            ),
        )


def test_lifecycle_reads_setup_order_from_ruleset_descriptor() -> None:
    setup_steps = (
        SetupStepKind.MUSTER_ARMIES,
        SetupStepKind.SELECT_SECONDARY_MISSIONS,
        SetupStepKind.SELECT_MISSION,
        SetupStepKind.CREATE_BATTLEFIELD,
        SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
        SetupStepKind.DECLARE_BATTLE_FORMATIONS,
        SetupStepKind.DEPLOY_ARMIES,
        SetupStepKind.REDEPLOY_UNITS,
        SetupStepKind.DETERMINE_FIRST_TURN,
        SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
    )
    lifecycle = _start_lifecycle(
        _config(ruleset_descriptor=_descriptor_with_sequences(setup_steps=setup_steps))
    )

    lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_missing_battle_phase_handler_is_not_silently_skipped() -> None:
    state = _battle_state()
    decisions = GameLifecycle().decision_controller
    flow = BattleRoundFlow(phase_handlers={})

    with pytest.raises(GameLifecycleError, match="missing handler"):
        flow.advance(state=state, decisions=decisions)

    assert state.current_battle_phase is BattlePhase.COMMAND


def test_lifecycle_stops_at_decision_request() -> None:
    lifecycle = _start_lifecycle()

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-a"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_descriptor_hash_is_recorded_in_lifecycle_replay_payloads() -> None:
    config = _config()
    lifecycle = _start_lifecycle(config)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert payload["config"] is not None
    assert payload["config"]["ruleset_descriptor"]["descriptor_hash"] == (
        config.ruleset_descriptor.descriptor_hash
    )
    assert payload["state"]["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_lifecycle_transition_guard_is_recorded_in_config_provenance() -> None:
    config = _config(max_lifecycle_transitions=127)
    lifecycle = _start_lifecycle(config)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert payload["config"] is not None
    assert payload["config"]["max_lifecycle_transitions"] == 127
    assert GameConfig.from_payload(payload["config"]).max_lifecycle_transitions == 127
    assert GameLifecycle.from_payload(payload).config.max_lifecycle_transitions == 127


def test_lifecycle_transition_guard_returns_typed_boundary_when_config_limit_is_too_low() -> None:
    lifecycle = _start_lifecycle(_config(max_lifecycle_transitions=1))

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert status.message == "Lifecycle reached its deterministic transition safety boundary."
    assert status.payload == {
        "unsupported_reason": "transition_budget_exhausted",
        "transition_budget": 1,
    }


def test_game_config_rejects_lifecycle_sequence_prerequisite_gaps() -> None:
    missing_secondary = _descriptor_with_sequences(
        setup_steps=(
            SetupStepKind.MUSTER_ARMIES,
            SetupStepKind.SELECT_MISSION,
            SetupStepKind.CREATE_BATTLEFIELD,
            SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
            SetupStepKind.DECLARE_BATTLE_FORMATIONS,
            SetupStepKind.DEPLOY_ARMIES,
            SetupStepKind.REDEPLOY_UNITS,
            SetupStepKind.DETERMINE_FIRST_TURN,
            SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
        )
    )
    with pytest.raises(GameLifecycleError, match="SELECT_SECONDARY_MISSIONS"):
        _config(ruleset_descriptor=missing_secondary)

    not_command_first = _descriptor_with_sequences(
        battle_phases=(
            BattlePhaseKind.MOVEMENT,
            BattlePhaseKind.COMMAND,
            BattlePhaseKind.FIGHT,
        )
    )
    with pytest.raises(GameLifecycleError, match="start with COMMAND"):
        _config(ruleset_descriptor=not_command_first)


def test_lifecycle_from_payload_rejects_config_state_ruleset_drift() -> None:
    lifecycle = _start_lifecycle()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    hash_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    hash_mismatch["state"]["ruleset_descriptor_hash"] = "0" * 64
    with pytest.raises(GameLifecycleError, match="ruleset hash"):
        GameLifecycle.from_payload(hash_mismatch)

    setup_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    setup_mismatch["state"]["setup_sequence"] = list(reversed(payload["state"]["setup_sequence"]))
    with pytest.raises(GameLifecycleError, match="setup sequence"):
        GameLifecycle.from_payload(setup_mismatch)

    battle_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    battle_mismatch["state"]["battle_phase_sequence"] = [
        BattlePhaseKind.COMMAND.value,
        BattlePhaseKind.SHOOTING.value,
        BattlePhaseKind.MOVEMENT.value,
        BattlePhaseKind.CHARGE.value,
        BattlePhaseKind.FIGHT.value,
    ]
    with pytest.raises(GameLifecycleError, match="battle phase sequence"):
        GameLifecycle.from_payload(battle_mismatch)


def test_lifecycle_from_payload_rejects_config_state_identity_drift() -> None:
    lifecycle = _start_lifecycle()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    game_id_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    game_id_mismatch["state"]["game_id"] = "other-game"
    with pytest.raises(GameLifecycleError, match="game_id"):
        GameLifecycle.from_payload(game_id_mismatch)

    player_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    player_mismatch["state"]["player_ids"] = ["player-a", "player-c"]
    with pytest.raises(GameLifecycleError, match="player_ids"):
        GameLifecycle.from_payload(player_mismatch)

    turn_order_mismatch = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    turn_order_mismatch["state"]["turn_order"] = ["player-b", "player-a"]
    with pytest.raises(GameLifecycleError, match="turn_order"):
        GameLifecycle.from_payload(turn_order_mismatch)

    tactical_count_mismatch = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    tactical_count_mismatch["state"]["tactical_secondary_draw_count"] = 3
    with pytest.raises(GameLifecycleError, match="tactical secondary draw count"):
        GameLifecycle.from_payload(tactical_count_mismatch)


def test_lifecycle_from_payload_rejects_mustered_army_state_drift() -> None:
    lifecycle = _start_lifecycle()
    lifecycle.advance_until_decision_or_terminal()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    missing_armies = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    missing_armies["state"]["army_definitions"] = []
    missing_armies["state"]["starting_strength_records"] = []
    with pytest.raises(GameLifecycleError, match=r"mustered army definitions|battlefield_state"):
        GameLifecycle.from_payload(missing_armies)

    army_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    army_mismatch["state"]["army_definitions"][0]["units"][0]["name"] = "Different Name"
    with pytest.raises(GameLifecycleError, match="army definitions"):
        GameLifecycle.from_payload(army_mismatch)


def test_lifecycle_and_command_handler_fail_fast_on_invalid_entry_points() -> None:
    lifecycle = GameLifecycle()
    with pytest.raises(GameLifecycleError, match="has not started"):
        lifecycle.advance_until_decision_or_terminal()

    config = _config()
    lifecycle.start(config)
    with pytest.raises(GameLifecycleError, match="already started"):
        lifecycle.start(config)

    _advance_to_battle(lifecycle)
    assert CommandPhaseHandler().phase is BattlePhase.COMMAND
    draw_status = _submit_pending(lifecycle, option_id="draw", result_number=3)
    draw_status = drain_pending_secondary_mission_setup(
        lifecycle,
        draw_status,
        result_id_prefix="decision-result-secondary-setup",
    )
    if (
        draw_status.decision_request is not None
        and draw_status.decision_request.decision_type == STRATAGEM_DECISION_TYPE
    ):
        _submit_pending(
            lifecycle,
            option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
            result_number=4,
        )
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    with pytest.raises(GameLifecycleError, match="only in the COMMAND phase"):
        CommandPhaseHandler().begin_phase(
            state=lifecycle.state,
            decisions=lifecycle.decision_controller,
        )


def test_lifecycle_status_payloads_are_serializable_and_fail_fast() -> None:
    advanced = LifecycleStatus.advanced(
        stage=GameLifecycleStage.SETUP,
        payload={"step": SetupStep.MUSTER_ARMIES.value},
    )
    terminal = LifecycleStatus.terminal(
        stage=GameLifecycleStage.COMPLETE,
        message="complete",
    )
    unsupported = LifecycleStatus.unsupported(
        stage=GameLifecycleStage.BATTLE,
        message="phase body unsupported",
    )

    for status in (advanced, terminal, unsupported):
        payload = json.loads(json.dumps(status.to_payload(), sort_keys=True))
        assert LifecycleStatus.from_payload(payload).to_payload() == status.to_payload()

    with pytest.raises(GameLifecycleError, match="requires a decision_request"):
        LifecycleStatus(
            stage=GameLifecycleStage.SETUP,
            status_kind=LifecycleStatusKind.WAITING_FOR_DECISION,
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        LifecycleStatus.terminal(stage=GameLifecycleStage.COMPLETE, message=" ")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        game_lifecycle_stage_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported GameLifecycleStage"):
        game_lifecycle_stage_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        lifecycle_status_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported LifecycleStatusKind"):
        lifecycle_status_kind_from_token("bad_kind")


__all__: list[str] = []
__all__ += ["ArmyMusterRequest", "BattlePhaseSequenceDescriptor", "ChargePhaseState"]
__all__ += ["ChargeRollRequest", "ChargeRollResult", "ChargingUnitSelection"]
__all__ += ["DEFAULT_MAX_LIFECYCLE_TRANSITIONS", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DetachmentSelection", "DiceRollManager"]
__all__ += ["FightPhaseState", "FightsFirstRegistry", "GameConfigPayload", "GameStatePayload"]
__all__ += ["GeometrySourceKind", "HeightSourceKind", "JsonValue", "MissionSetup"]
__all__ += ["ModelGeometryCatalogRecord", "ModelGeometryCatalogRecordPayload"]
__all__ += ["ModelProfileSelection", "MovementPhaseState", "ObjectiveControlTiming"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "PlaceholderPhaseHandler", "RulesetDescriptor"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupCompletionGate"]
__all__ += ["SetupSequenceDescriptor", "ShootingPhaseState"]
__all__ += ["TACTICAL_SECONDARY_DRAW_DECISION_TYPE", "UnitMusterSelection", "WargearSelection"]
__all__ += ["_advance_to_secondary_mission_step", "_army_muster_requests", "_battle_flow"]
__all__ += ["_battle_lifecycle_for_consistency", "_choose_secondaries"]
__all__ += ["_complete_setup_through_gate", "_decline_stratagem_window_if_pending"]
__all__ += ["_lifecycle_is_in_battle", "_mission_setup", "_pending_request"]
__all__ += ["_phase_state_consistency_payload", "_public_secondary_choices", "_request_payload"]
__all__ += ["_state_battle_phase", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_deterministic_battlefield_scenario"]
__all__ += ["ensure_army_mustered_events_for_fixture", "inspect", "replace"]
__all__ += ["seed_completed_fight_phase", "submit_all_deployments_if_pending"]
