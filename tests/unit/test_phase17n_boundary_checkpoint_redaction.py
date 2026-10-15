from __future__ import annotations

from tests.shared.category_migration.phase17n_boundary_checkpoint_redaction import (
    FROZEN_RULES_UNIT_COMPONENTS_POLICY,
    MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    MORTAL_WOUND_APPLICATION_STARTED_EVENT,
    MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    ROLE_POLICY_BY_ROLE,
    DamageApplication,
    DamageApplicationLogicalDeathTransition,
    DamageKind,
    DecisionOption,
    DecisionRecord,
    DecisionRequest,
    DecisionResult,
    EventRecord,
    FeelNoPainSource,
    GameLifecycleError,
    GameLifecycleStage,
    JsonValue,
    LifecycleStatus,
    ModelDestructionCauseKind,
    ModelLogicalDeathRecord,
    ModelPlacement,
    MortalWoundApplicationProgress,
    MortalWoundLogicalDeathCauseBinding,
    MortalWoundTargetLineage,
    Pose,
    PrimaryMissionBoundaryCheckpoint,
    PrincipalRole,
    SecondaryMissionCardState,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    ViewerContext,
    _administrator_viewer,
    _assert_internal_model_destruction_authority_absent,
    _assert_internal_secondary_authority_absent,
    _assert_owner_score_context_preserved,
    _pending_fnp_request_with_logical_death_authority,
    _tactical_score_context,
    _tactical_score_request,
    build_feel_no_pain_request,
    canonical_json,
    canonical_payload_sha256,
    model_destruction_cause_id,
    model_logical_death_boundary_id,
    public_decision_request_payload,
    public_decision_request_view,
    public_event_record_payload,
    public_victory_point_transaction_payload,
    pytest,
    redacted_lifecycle_status,
    replace,
    validate_json_value,
)


def test_phase17n_model_logical_death_event_is_private_for_every_adapter_viewer() -> None:
    payload: dict[str, JsonValue] = {"private_boundary": "model-logical-death:private"}

    for viewer in (ViewerContext.for_player("player-a"), _administrator_viewer()):
        assert (
            public_event_record_payload(
                event_id="event-000001",
                event_type=MODEL_LOGICAL_DEATH_RECORDED_EVENT,
                payload=payload,
                viewer=viewer,
            )
            is None
        )


def test_phase17n_mortal_wound_start_authority_is_private_for_every_adapter_viewer() -> None:
    payload: dict[str, JsonValue] = {
        "game_id": "phase17n-private-mortal-wound-start",
        "application_id": "phase17n-private-mortal-wound-application",
        "source_context": {"private_producer": "internal-cause-root"},
    }

    for viewer in (
        ViewerContext.for_player("player-a"),
        ViewerContext.for_player("player-b"),
        _administrator_viewer(),
    ):
        assert (
            public_event_record_payload(
                event_id="event-000001",
                event_type=MORTAL_WOUND_APPLICATION_STARTED_EVENT,
                payload=payload,
                viewer=viewer,
            )
            is None
        )


def test_phase17n_mortal_wound_allocation_authority_is_private_for_every_viewer() -> None:
    payload: dict[str, JsonValue] = {
        "occurrence_id": "phase17n-private-allocation:allocation:000001",
        "selected_model_id": "phase17n-private-model",
        "feel_no_pain_sources": [{"source_id": "phase17n-private-fnp"}],
    }

    for viewer in (
        ViewerContext.for_player("player-a"),
        ViewerContext.for_player("player-b"),
        _administrator_viewer(),
    ):
        assert (
            public_event_record_payload(
                event_id="event-000001",
                event_type=MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
                payload=payload,
                viewer=viewer,
            )
            is None
        )


def test_contract_10_checkpoint_without_card_witness_preserves_legacy_hash() -> None:
    card = SecondaryMissionCardState.active_fixed(
        player_id="player-a",
        secondary_mission_id="legacy-secondary-card",
    )
    checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind="objective_control",
        game_id="phase17n-legacy-checkpoint-game",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=1,
        phase="command",
        battlefield_id="phase17n-legacy-checkpoint-battlefield",
        model_states=(),
        attached_unit_formation_jsons=(),
        battle_shocked_unit_instance_ids=(),
        advanced_unit_state_jsons=(),
        fell_back_unit_state_jsons=(),
        shot_unit_instance_ids=(),
        objective_control_modifier_sources=(),
        active_primary_marker_jsons=(),
        active_secondary_mission_card_jsons=(canonical_json(card.to_payload()),),
        completed_mission_action_state_jsons=(),
        primary_unit_destruction_state_jsons=(),
        starting_strength_record_jsons=(),
        active_secondary_mission_ids=("legacy-secondary-card",),
        mission_action_prior_use_jsons=(),
    )
    legacy_payload = checkpoint.to_payload()
    del legacy_payload["active_secondary_mission_card_jsons"]
    del legacy_payload["completed_mission_action_state_jsons"]
    del legacy_payload["primary_unit_destruction_state_jsons"]
    del legacy_payload["starting_strength_record_jsons"]
    legacy_content = dict(legacy_payload)
    del legacy_content["checkpoint_id"]
    del legacy_content["checkpoint_hash"]
    legacy_hash = canonical_payload_sha256(legacy_content)
    legacy_payload["checkpoint_id"] = f"primary-mission-boundary:{legacy_hash}"
    legacy_payload["checkpoint_hash"] = legacy_hash

    restored = PrimaryMissionBoundaryCheckpoint.from_payload(legacy_payload)

    assert restored.active_secondary_mission_card_jsons == ()
    assert restored.completed_mission_action_state_jsons == ()
    assert restored.primary_unit_destruction_state_jsons == ()
    assert restored.starting_strength_record_jsons == ()
    assert restored.to_payload() == legacy_payload


def test_phase17n_action_decline_evidence_is_owner_and_administrator_only() -> None:
    payload: dict[str, JsonValue] = {
        "game_id": "phase17n-redaction-game",
        "player_id": "player-a",
        "battle_round": 1,
        "phase": "shooting",
        "request_id": "decision-request-000001",
        "result_id": "decline-result-000001",
        "selected_option_id": "continue_to_shooting",
        "mission_action_opportunity_decline_evidence": {
            "request_authority": {
                "active_secondary_mission_ids": ["secret-secondary-card"],
            },
        },
    }

    owner_event = public_event_record_payload(
        event_id="phase17n-decline-event",
        event_type=MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
        payload=payload,
        viewer=ViewerContext.for_player("player-a"),
    )
    assert owner_event is not None
    assert owner_event["payload"] == payload

    assert (
        public_event_record_payload(
            event_id="phase17n-decline-event",
            event_type=MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
            payload=payload,
            viewer=ViewerContext.for_player("player-b"),
        )
        is None
    )

    administrator = ViewerContext(
        principal_id="phase17n-administrator",
        role=PrincipalRole.ADMINISTRATOR,
        viewer_player_id=None,
        policy=ROLE_POLICY_BY_ROLE[PrincipalRole.ADMINISTRATOR],
    )
    administrator_event = public_event_record_payload(
        event_id="phase17n-decline-event",
        event_type=MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
        payload=payload,
        viewer=administrator,
    )
    assert administrator_event is not None
    assert administrator_event["payload"] == payload


def test_phase17n_tactical_score_decision_is_viewer_safe_in_events_and_projection() -> None:
    request = _tactical_score_request()
    result = DecisionResult.for_request(
        result_id="phase17n-tactical-score-result",
        request=request,
        selected_option_id="score:beacon",
    )
    owner = ViewerContext.for_player("player-a")
    opponent = ViewerContext.for_player("player-b")
    administrator = _administrator_viewer()
    raw_request_payload = validate_json_value(request.to_payload())
    assert isinstance(raw_request_payload, dict)

    owner_requested = public_event_record_payload(
        event_id="phase17n-tactical-score-requested-event",
        event_type="decision_requested",
        payload=raw_request_payload,
        viewer=owner,
    )
    assert owner_requested is not None
    owner_request_payload = owner_requested["payload"]
    assert isinstance(owner_request_payload, dict)
    _assert_internal_secondary_authority_absent(owner_request_payload)
    _assert_owner_score_context_preserved(owner_request_payload["payload"])
    options = owner_request_payload["options"]
    assert isinstance(options, list)
    assert options
    for option in options:
        assert isinstance(option, dict)
        _assert_owner_score_context_preserved(option["payload"])

    assert (
        public_event_record_payload(
            event_id="phase17n-tactical-score-requested-event",
            event_type="decision_requested",
            payload=raw_request_payload,
            viewer=opponent,
        )
        is None
    )
    administrator_requested = public_event_record_payload(
        event_id="phase17n-tactical-score-requested-event",
        event_type="decision_requested",
        payload=raw_request_payload,
        viewer=administrator,
    )
    assert administrator_requested is not None
    assert administrator_requested["payload"] == request.to_payload()

    raw_record_payload = validate_json_value(
        {
            "record_id": "phase17n-tactical-score-record",
            "request": request.to_payload(),
            "result": result.to_payload(),
        }
    )
    assert isinstance(raw_record_payload, dict)
    record_payload = raw_record_payload
    owner_recorded = public_event_record_payload(
        event_id="phase17n-tactical-score-recorded-event",
        event_type="decision_recorded",
        payload=record_payload,
        viewer=owner,
    )
    assert owner_recorded is not None
    owner_record_payload = owner_recorded["payload"]
    assert isinstance(owner_record_payload, dict)
    _assert_internal_secondary_authority_absent(owner_record_payload)
    recorded_result = owner_record_payload["result"]
    assert isinstance(recorded_result, dict)
    _assert_owner_score_context_preserved(recorded_result["payload"])

    assert (
        public_event_record_payload(
            event_id="phase17n-tactical-score-recorded-event",
            event_type="decision_recorded",
            payload=record_payload,
            viewer=opponent,
        )
        is None
    )
    administrator_recorded = public_event_record_payload(
        event_id="phase17n-tactical-score-recorded-event",
        event_type="decision_recorded",
        payload=record_payload,
        viewer=administrator,
    )
    assert administrator_recorded is not None
    assert administrator_recorded["payload"] == record_payload

    owner_projection = public_decision_request_view(request, viewer=owner)
    _assert_internal_secondary_authority_absent(owner_projection)
    _assert_owner_score_context_preserved(owner_projection["payload"])
    opponent_projection = public_decision_request_view(request, viewer=opponent)
    assert opponent_projection["decision_type"] == "hidden_decision"
    assert opponent_projection["options"] == []
    administrator_projection = public_decision_request_view(request, viewer=administrator)
    assert administrator_projection["payload"] == request.payload
    assert administrator_projection["options"] == [
        option.to_payload() for option in request.options
    ]


__all__: list[str] = []
__all__ += ["DamageApplication", "DamageApplicationLogicalDeathTransition", "DamageKind"]
__all__ += ["DecisionOption", "DecisionRecord", "DecisionRequest", "EventRecord"]
__all__ += ["FROZEN_RULES_UNIT_COMPONENTS_POLICY", "FeelNoPainSource", "GameLifecycleError"]
__all__ += ["GameLifecycleStage", "LifecycleStatus", "ModelDestructionCauseKind"]
__all__ += ["ModelLogicalDeathRecord", "ModelPlacement", "MortalWoundApplicationProgress"]
__all__ += ["MortalWoundLogicalDeathCauseBinding", "MortalWoundTargetLineage"]
__all__ += ["PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "Pose", "VictoryPointSourceKind"]
__all__ += ["VictoryPointTransaction", "_assert_internal_model_destruction_authority_absent"]
__all__ += ["_pending_fnp_request_with_logical_death_authority", "_tactical_score_context"]
__all__ += ["build_feel_no_pain_request", "model_destruction_cause_id"]
__all__ += ["model_logical_death_boundary_id", "public_decision_request_payload"]
__all__ += ["public_victory_point_transaction_payload", "pytest", "redacted_lifecycle_status"]
__all__ += ["replace"]
