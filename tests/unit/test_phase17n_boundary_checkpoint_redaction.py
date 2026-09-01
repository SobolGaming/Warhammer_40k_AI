from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.projection import public_decision_request_view
from warhammer40k_core.adapters.redaction import (
    public_decision_request_payload,
    public_event_record_payload,
    public_victory_point_transaction_payload,
    redacted_lifecycle_status,
)
from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageKind,
    FeelNoPainSource,
    MortalWoundApplicationProgress,
    build_feel_no_pain_request,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
    model_destruction_cause_id,
)
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    DamageApplicationLogicalDeathTransition,
    ModelLogicalDeathRecord,
    model_logical_death_boundary_id,
)
from warhammer40k_core.engine.mortal_wound_application_authority import (
    MORTAL_WOUND_APPLICATION_STARTED_EVENT,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
)
from warhammer40k_core.engine.mortal_wound_target_lineage import (
    FROZEN_RULES_UNIT_COMPONENTS_POLICY,
    MortalWoundTargetLineage,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.primary_mission_action_decline_integrity import (
    MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardState,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.geometry.pose import Pose


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


def test_phase17n_boundary_checkpoint_is_owner_and_administrator_only() -> None:
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
    )
    payload = checkpoint.to_payload()

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


def _tactical_score_request() -> DecisionRequest:
    context = _tactical_score_context()
    options = (
        DecisionOption(
            option_id="score:beacon",
            label="Score beacon",
            payload={**context, "score": True},
        ),
        DecisionOption(
            option_id="retain:beacon",
            label="Retain beacon",
            payload={**context, "score": False},
        ),
    )
    return DecisionRequest(
        request_id="phase17n-tactical-score-request",
        decision_type="score_tactical_secondary_mission",
        actor_id="player-a",
        payload={
            **context,
            "legal_option_ids": [option.option_id for option in options],
        },
        options=options,
    )


def _tactical_score_context() -> dict[str, JsonValue]:
    return {
        "achievement_id": "phase17n-tactical-achievement",
        "game_id": "phase17n-tactical-score-redaction",
        "player_id": "player-a",
        "active_player_id": "player-a",
        "secondary_mission_id": "beacon",
        "mode": "tactical",
        "battle_round": 2,
        "phase": "fight",
        "card_battle_round": 2,
        "victory_points": 5,
        "scoring_rule_id": "beacon-rule",
        "scoring_rule_condition": "beacon-condition",
        "scoring_rule_source_id": "beacon-source",
        "scoring_timing": "turn_end",
        "source_id": "beacon",
        "evidence": {
            "scoring_commit_checkpoint_id": "primary-mission-boundary:secret",
            "scoring_commit_checkpoint_hash": "a" * 64,
            "secondary_scoring_state_evidence_id": "secondary-evidence:secret",
            "secondary_scoring_state_evidence_hash": "b" * 64,
            "evidence_by_rule": {"beacon": {"selected_unit_instance_ids": ["secret-owner-unit"]}},
        },
    }


def _assert_internal_secondary_authority_absent(payload: object) -> None:
    encoded = canonical_json(validate_json_value(payload))
    for key in (
        "scoring_commit_checkpoint_id",
        "scoring_commit_checkpoint_hash",
        "secondary_scoring_state_evidence_id",
        "secondary_scoring_state_evidence_hash",
    ):
        assert f'"{key}"' not in encoded


def _assert_owner_score_context_preserved(payload: JsonValue) -> None:
    assert isinstance(payload, dict)
    assert payload["achievement_id"] == "phase17n-tactical-achievement"
    assert payload["secondary_mission_id"] == "beacon"
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["evidence_by_rule"] == {
        "beacon": {"selected_unit_instance_ids": ["secret-owner-unit"]}
    }


def _pending_fnp_request_with_logical_death_authority() -> tuple[DecisionRequest, str, str]:
    game_id = "phase17n-private-fnp-game"
    application_id = "phase17n-private-fnp-application"
    physical_unit_id = "army-a:unit-a"
    destroyed_model_id = f"{physical_unit_id}:model-a"
    next_model_id = f"{physical_unit_id}:model-b"
    damage = DamageApplication(
        target_unit_instance_id=physical_unit_id,
        model_instance_id=destroyed_model_id,
        damage_kind=DamageKind.MORTAL,
        requested_damage=1,
        wounds_lost=1,
        excess_damage_lost=0,
        starting_wounds_remaining=1,
        final_wounds_remaining=0,
        destroyed=True,
    )
    cause_id = model_destruction_cause_id(
        game_id=game_id,
        cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
        producer_id=application_id,
        model_instance_id=destroyed_model_id,
    )
    boundary_id = model_logical_death_boundary_id(
        game_id=game_id,
        cause_id=cause_id,
        model_instance_id=destroyed_model_id,
    )
    logical_death = ModelLogicalDeathRecord(
        boundary_id=boundary_id,
        game_id=game_id,
        cause_id=cause_id,
        cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
        producer_id=application_id,
        model_instance_id=destroyed_model_id,
        physical_unit_instance_id=physical_unit_id,
        rules_unit_instance_id=physical_unit_id,
        destroyed_model_placement=ModelPlacement(
            army_id="army-a",
            player_id="player-a",
            unit_instance_id=physical_unit_id,
            model_instance_id=destroyed_model_id,
            pose=Pose.at(x=12.0, y=8.0),
        ),
        placement_retained=True,
        transition=DamageApplicationLogicalDeathTransition(damage_application=damage.to_payload()),
    )
    logical_death_event = EventRecord(
        event_id="event-000001",
        event_type=MODEL_LOGICAL_DEATH_RECORDED_EVENT,
        payload=validate_json_value(logical_death.to_payload()),
    )
    progress = MortalWoundApplicationProgress(
        application_id=application_id,
        source_rule_id="phase17n-private-fnp-source",
        source_context={"source_result_id": "phase17n-private-fnp-source-result"},
        target_unit_instance_id=physical_unit_id,
        defender_player_id="player-a",
        mortal_wounds=2,
        remaining_mortal_wounds=1,
        spill_over=True,
        destruction_evidence=None,
        logical_death_events=(logical_death_event,),
        logical_death_cause_binding=MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
            producer_id=application_id,
        ),
        applications=(damage,),
        target_lineage=MortalWoundTargetLineage(
            policy=FROZEN_RULES_UNIT_COMPONENTS_POLICY,
            canonical_target_unit_instance_id=physical_unit_id,
            owner_player_id="player-a",
            component_unit_instance_ids=(physical_unit_id,),
            character_component_unit_instance_ids=(),
        ),
    )
    return (
        build_feel_no_pain_request(
            request_id="phase17n-private-fnp-request",
            defender_player_id="player-a",
            lost_wound_context=validate_json_value(
                progress.to_feel_no_pain_context(
                    model_instance_id=next_model_id,
                    allocation_occurrence={
                        "private_selected_model_id": next_model_id,
                        "private_fnp_source_id": "phase17n-private-fnp-source-a",
                    },
                )
            ),
            sources=(
                FeelNoPainSource(
                    source_id="phase17n-private-fnp-source-a",
                    threshold=5,
                ),
                FeelNoPainSource(
                    source_id="phase17n-private-fnp-source-b",
                    threshold=6,
                ),
            ),
            decline_allowed=False,
        ),
        cause_id,
        boundary_id,
    )


def _assert_internal_model_destruction_authority_absent(
    payload: object,
    *,
    cause_id: str,
    boundary_id: str,
) -> None:
    encoded = canonical_json(validate_json_value(payload))
    for key in (
        "allocation_occurrence",
        "logical_death_cause_binding",
        "logical_death_event",
        "logical_death_events",
        "model_destruction_cause_authorities",
        "model_destruction_cause_id",
        "parent_model_destruction_cause_id",
    ):
        assert f'"{key}"' not in encoded
    assert MODEL_LOGICAL_DEATH_RECORDED_EVENT not in encoded
    assert cause_id not in encoded
    assert boundary_id not in encoded


def _administrator_viewer() -> ViewerContext:
    return ViewerContext(
        principal_id="phase17n-administrator",
        role=PrincipalRole.ADMINISTRATOR,
        viewer_player_id=None,
        policy=ROLE_POLICY_BY_ROLE[PrincipalRole.ADMINISTRATOR],
    )
