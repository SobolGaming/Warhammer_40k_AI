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


def test_phase17n_pending_fnp_logical_death_authority_is_private_on_every_public_path() -> None:
    request, cause_id, boundary_id = _pending_fnp_request_with_logical_death_authority()
    result = DecisionResult.for_request(
        result_id="phase17n-private-fnp-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    record = DecisionRecord(
        record_id="decision-record-000001",
        request=request,
        result=result,
    )
    raw_request_value = validate_json_value(request.to_payload())
    raw_record_value = validate_json_value(record.to_payload())
    assert isinstance(raw_request_value, dict)
    assert isinstance(raw_record_value, dict)
    raw_request = raw_request_value
    raw_record = raw_record_value
    assert '"allocation_occurrence"' in canonical_json(raw_request)
    assert '"logical_death_events"' in canonical_json(raw_request)
    assert cause_id in canonical_json(raw_request)
    assert boundary_id in canonical_json(raw_request)

    owner = ViewerContext.for_player("player-a")
    opponent = ViewerContext.for_player("player-b")
    administrator = _administrator_viewer()
    for viewer in (owner, opponent, administrator):
        _assert_internal_model_destruction_authority_absent(
            public_decision_request_payload(request, viewer=viewer),
            cause_id=cause_id,
            boundary_id=boundary_id,
        )
        _assert_internal_model_destruction_authority_absent(
            public_decision_request_view(request, viewer=viewer),
            cause_id=cause_id,
            boundary_id=boundary_id,
        )
        _assert_internal_model_destruction_authority_absent(
            redacted_lifecycle_status(
                LifecycleStatus.invalid(
                    stage=GameLifecycleStage.BATTLE,
                    message="Private FNP authority diagnostic",
                    payload={"request": raw_request, "record": raw_record},
                ),
                viewer=viewer,
            ),
            cause_id=cause_id,
            boundary_id=boundary_id,
        )

        requested = public_event_record_payload(
            event_id="phase17n-private-fnp-requested",
            event_type="decision_requested",
            payload=raw_request,
            viewer=viewer,
        )
        recorded = public_event_record_payload(
            event_id="phase17n-private-fnp-recorded",
            event_type="decision_recorded",
            payload=raw_record,
            viewer=viewer,
        )
        assert requested is not None
        assert recorded is not None
        _assert_internal_model_destruction_authority_absent(
            requested,
            cause_id=cause_id,
            boundary_id=boundary_id,
        )
        _assert_internal_model_destruction_authority_absent(
            recorded,
            cause_id=cause_id,
            boundary_id=boundary_id,
        )

    assert request.to_payload() == raw_request
    assert record.to_payload() == raw_record


def test_phase17n_public_fixed_secondary_metadata_excludes_only_authority_commitments() -> None:
    public_metadata = {
        "secondary_scoring_provider_kind": "legacy_phase11f",
        "secondary_mission_id": "bring-it-down",
        "scoring_rule_id": "bring-it-down-fixed",
    }
    transaction = VictoryPointTransaction(
        transaction_id="victory-point:player-a:round-01:000001",
        player_id="player-a",
        battle_round=1,
        phase="command",
        amount=4,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        source_id="bring-it-down",
        scoring_timing="secondary_mission_score",
        hidden=True,
        metadata={
            **public_metadata,
            "scoring_commit_checkpoint_id": "primary-mission-boundary:secret",
            "scoring_commit_checkpoint_hash": "a" * 64,
            "secondary_scoring_state_evidence_id": "secondary-evidence:secret",
            "secondary_scoring_state_evidence_hash": "b" * 64,
        },
    )

    payload = public_victory_point_transaction_payload(
        transaction,
        viewer=ViewerContext.for_player("player-b"),
        domain_viewer_player_id="player-b",
        secondary_mission_choices_revealed=True,
    )

    assert payload["hidden"] is False
    assert payload["metadata"] == public_metadata


@pytest.mark.parametrize("modifier_scope_id", [None, "objective-control:test-scope"])
def test_phase17n_boundary_checkpoint_is_owner_and_administrator_only(
    modifier_scope_id: str | None,
) -> None:
    owner_card = SecondaryMissionCardState.active_fixed(
        player_id="player-a",
        secondary_mission_id="secret-secondary-card",
    )
    opponent_card = SecondaryMissionCardState.active_fixed(
        player_id="player-b",
        secondary_mission_id="opponent-secret-secondary-card",
    )
    checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind="objective_control",
        game_id="phase17n-redaction-game",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=1,
        phase="shooting",
        battlefield_id="phase17n-redaction-battlefield",
        model_states=(),
        attached_unit_formation_jsons=(),
        battle_shocked_unit_instance_ids=(),
        advanced_unit_state_jsons=(),
        fell_back_unit_state_jsons=(),
        shot_unit_instance_ids=(),
        objective_control_modifier_sources=(),
        active_primary_marker_jsons=(),
        active_secondary_mission_card_jsons=(
            canonical_json(owner_card.to_payload()),
            canonical_json(opponent_card.to_payload()),
        ),
        completed_mission_action_state_jsons=(),
        primary_unit_destruction_state_jsons=(),
        starting_strength_record_jsons=(),
        active_secondary_mission_ids=("secret-secondary-card",),
        mission_action_prior_use_jsons=(),
        objective_control_modifier_scope_id=modifier_scope_id,
    )
    payload = checkpoint.to_payload()
    # Every serialized content field participates in the checkpoint identity;
    # a boundary with no modifier evaluation has no source scope to serialize.
    assert ("objective_control_modifier_scope_id" in payload) is (modifier_scope_id is not None)
    assert checkpoint.checkpoint_hash == canonical_payload_sha256(
        {
            key: value
            for key, value in payload.items()
            if key not in {"checkpoint_id", "checkpoint_hash"}
        }
    )
    for invalid_scope in (None, "", 7):
        with pytest.raises(GameLifecycleError, match="objective_control_modifier_scope_id"):
            PrimaryMissionBoundaryCheckpoint.from_payload(
                {**payload, "objective_control_modifier_scope_id": invalid_scope}
            )

    owner_event = public_event_record_payload(
        event_id="phase17n-checkpoint-event",
        event_type=PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        payload=payload,
        viewer=ViewerContext.for_player("player-a"),
    )
    assert owner_event is not None
    owner_payload = owner_event["payload"]
    assert isinstance(owner_payload, dict)
    assert owner_payload != payload
    owner_checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(owner_payload)
    assert "active_secondary_mission_card_jsons" not in owner_payload
    assert "completed_mission_action_state_jsons" not in owner_payload
    assert "primary_unit_destruction_state_jsons" not in owner_payload
    assert "starting_strength_record_jsons" not in owner_payload
    assert owner_checkpoint.active_secondary_mission_card_jsons == ()
    assert owner_checkpoint.completed_mission_action_state_jsons == ()
    assert owner_checkpoint.primary_unit_destruction_state_jsons == ()
    assert owner_checkpoint.starting_strength_record_jsons == ()
    assert owner_checkpoint.active_secondary_mission_ids == (owner_card.secondary_mission_id,)

    assert (
        public_event_record_payload(
            event_id="phase17n-checkpoint-event",
            event_type=PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
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
        event_id="phase17n-checkpoint-event",
        event_type=PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        payload=payload,
        viewer=administrator,
    )
    assert administrator_event is not None
    assert administrator_event["payload"] == payload


def test_phase17n_nested_scoring_commit_checkpoint_is_viewer_scoped() -> None:
    owner_card = replace(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="beacon",
            battle_round=2,
            source_result_id="phase17n-owner-card",
        ),
        selection_payload={"beacon_unit_instance_id": "secret-owner-unit"},
    )
    checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind="primary_scoring_commit",
        game_id="phase17n-scoring-commit-redaction",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        phase="fight",
        battlefield_id="phase17n-redaction-battlefield",
        model_states=(),
        attached_unit_formation_jsons=(),
        battle_shocked_unit_instance_ids=(),
        advanced_unit_state_jsons=(),
        fell_back_unit_state_jsons=(),
        shot_unit_instance_ids=(),
        objective_control_modifier_sources=(),
        active_primary_marker_jsons=(),
        active_secondary_mission_card_jsons=(),
        completed_mission_action_state_jsons=(),
        primary_unit_destruction_state_jsons=(),
        starting_strength_record_jsons=(),
        active_secondary_mission_ids=(owner_card.secondary_mission_id,),
        mission_action_prior_use_jsons=(),
    )
    payload: dict[str, JsonValue] = {
        "objective_control_record_id": "phase17n-objective-control-record",
        "scoring_boundary_kind": "ordinary",
        "checkpoint": checkpoint.to_payload(),
    }

    owner_event = public_event_record_payload(
        event_id="phase17n-scoring-commit-event",
        event_type=PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
        payload=payload,
        viewer=ViewerContext.for_player("player-a"),
    )
    assert owner_event is not None
    owner_payload = owner_event["payload"]
    assert isinstance(owner_payload, dict)
    owner_checkpoint_payload = owner_payload["checkpoint"]
    assert isinstance(owner_checkpoint_payload, dict)
    assert "active_secondary_mission_card_jsons" not in owner_checkpoint_payload
    assert owner_checkpoint_payload == checkpoint.to_payload()

    assert (
        public_event_record_payload(
            event_id="phase17n-scoring-commit-event",
            event_type=PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
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
        event_id="phase17n-scoring-commit-event",
        event_type=PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
        payload=payload,
        viewer=administrator,
    )
    assert administrator_event is not None
    assert administrator_event["payload"] == payload


def test_phase17n_tactical_score_event_hides_internal_authority_and_opponent_selection() -> None:
    transaction = VictoryPointTransaction(
        transaction_id="victory-point:player-a:round-02:000001",
        player_id="player-a",
        battle_round=2,
        phase="fight",
        amount=5,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        source_id="beacon",
        scoring_timing="turn_end",
        metadata={
            "scoring_commit_checkpoint_id": "primary-mission-boundary:secret-checkpoint",
            "scoring_commit_checkpoint_hash": "a" * 64,
            "secondary_scoring_state_evidence_id": "secondary-evidence:secret",
            "secondary_scoring_state_evidence_hash": "b" * 64,
        },
    )
    active_card = replace(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="beacon",
            battle_round=2,
            source_result_id="phase17n-beacon-draw",
        ),
        selection_payload={"beacon_unit_instance_id": "secret-owner-unit"},
    )
    scored_card = active_card.score(transaction_id=transaction.transaction_id)
    raw_payload = validate_json_value(
        {
            "game_id": "phase17n-tactical-score-redaction",
            "player_id": "player-a",
            "active_player_id": "player-a",
            "battle_round": 2,
            "phase": "fight",
            "achievement_context": _tactical_score_context(),
            "secondary_mission_card_state": scored_card.to_payload(),
            "victory_point_transaction": transaction.to_payload(),
            "discarded_after_score": True,
        }
    )
    assert isinstance(raw_payload, dict)
    payload = raw_payload

    owner_event = public_event_record_payload(
        event_id="phase17n-tactical-score-event",
        event_type="tactical_secondary_mission_scored",
        payload=payload,
        viewer=ViewerContext.for_player("player-a"),
    )
    assert owner_event is not None
    owner_payload = owner_event["payload"]
    assert isinstance(owner_payload, dict)
    owner_transaction = owner_payload["victory_point_transaction"]
    assert isinstance(owner_transaction, dict)
    owner_metadata = owner_transaction["metadata"]
    assert isinstance(owner_metadata, dict)
    _assert_internal_secondary_authority_absent(owner_metadata)
    owner_achievement = owner_payload["achievement_context"]
    assert isinstance(owner_achievement, dict)
    _assert_internal_secondary_authority_absent(owner_achievement)
    owner_evidence = owner_achievement["evidence"]
    assert isinstance(owner_evidence, dict)
    assert owner_evidence["evidence_by_rule"] == {
        "beacon": {"selected_unit_instance_ids": ["secret-owner-unit"]}
    }
    owner_card_payload = owner_payload["secondary_mission_card_state"]
    assert isinstance(owner_card_payload, dict)
    assert owner_card_payload["selection_payload"] == active_card.selection_payload

    opponent_event = public_event_record_payload(
        event_id="phase17n-tactical-score-event",
        event_type="tactical_secondary_mission_scored",
        payload=payload,
        viewer=ViewerContext.for_player("player-b"),
    )
    assert opponent_event is not None
    opponent_payload = opponent_event["payload"]
    assert isinstance(opponent_payload, dict)
    assert "achievement_context" not in opponent_payload
    opponent_transaction = opponent_payload["victory_point_transaction"]
    assert isinstance(opponent_transaction, dict)
    opponent_metadata = opponent_transaction["metadata"]
    assert isinstance(opponent_metadata, dict)
    _assert_internal_secondary_authority_absent(opponent_metadata)
    opponent_card_payload = opponent_payload["secondary_mission_card_state"]
    assert isinstance(opponent_card_payload, dict)
    assert opponent_card_payload["selection_payload"] is None

    administrator = ViewerContext(
        principal_id="phase17n-administrator",
        role=PrincipalRole.ADMINISTRATOR,
        viewer_player_id=None,
        policy=ROLE_POLICY_BY_ROLE[PrincipalRole.ADMINISTRATOR],
    )
    administrator_event = public_event_record_payload(
        event_id="phase17n-tactical-score-event",
        event_type="tactical_secondary_mission_scored",
        payload=payload,
        viewer=administrator,
    )
    assert administrator_event is not None
    assert administrator_event["payload"] == payload


def test_phase17n_tactical_score_decline_event_is_owner_safe_and_opponent_hidden() -> None:
    card = replace(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="beacon",
            battle_round=2,
            source_result_id="phase17n-beacon-draw",
        ),
        selection_payload={"beacon_unit_instance_id": "secret-owner-unit"},
    )
    raw_payload = validate_json_value(
        {
            "game_id": "phase17n-tactical-score-redaction",
            "player_id": "player-a",
            "active_player_id": "player-a",
            "battle_round": 2,
            "phase": "fight",
            "achievement_context": _tactical_score_context(),
            "secondary_mission_card_state": card.to_payload(),
            "retained": True,
        }
    )
    assert isinstance(raw_payload, dict)
    payload = raw_payload

    owner_event = public_event_record_payload(
        event_id="phase17n-tactical-score-declined-event",
        event_type="tactical_secondary_mission_score_declined",
        payload=payload,
        viewer=ViewerContext.for_player("player-a"),
    )
    assert owner_event is not None
    owner_payload = owner_event["payload"]
    assert isinstance(owner_payload, dict)
    _assert_internal_secondary_authority_absent(owner_payload)
    owner_card = owner_payload["secondary_mission_card_state"]
    assert isinstance(owner_card, dict)
    assert owner_card["selection_payload"] == card.selection_payload
    _assert_owner_score_context_preserved(owner_payload["achievement_context"])

    assert (
        public_event_record_payload(
            event_id="phase17n-tactical-score-declined-event",
            event_type="tactical_secondary_mission_score_declined",
            payload=payload,
            viewer=ViewerContext.for_player("player-b"),
        )
        is None
    )
    administrator_event = public_event_record_payload(
        event_id="phase17n-tactical-score-declined-event",
        event_type="tactical_secondary_mission_score_declined",
        payload=payload,
        viewer=_administrator_viewer(),
    )
    assert administrator_event is not None
    assert administrator_event["payload"] == payload


__all__: list[str] = []
__all__ += ["DamageApplication", "DamageApplicationLogicalDeathTransition", "DamageKind"]
__all__ += ["DecisionOption", "DecisionRequest", "EventRecord"]
__all__ += ["FROZEN_RULES_UNIT_COMPONENTS_POLICY", "FeelNoPainSource"]
__all__ += ["MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT", "MODEL_LOGICAL_DEATH_RECORDED_EVENT"]
__all__ += ["MORTAL_WOUND_APPLICATION_STARTED_EVENT", "MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE"]
__all__ += ["ModelDestructionCauseKind", "ModelLogicalDeathRecord", "ModelPlacement"]
__all__ += ["MortalWoundApplicationProgress", "MortalWoundLogicalDeathCauseBinding"]
__all__ += ["MortalWoundTargetLineage", "Pose", "_tactical_score_request"]
__all__ += ["build_feel_no_pain_request", "model_destruction_cause_id"]
__all__ += ["model_logical_death_boundary_id"]
