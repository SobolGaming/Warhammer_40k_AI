from __future__ import annotations

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.redaction import public_event_record_payload
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.primary_mission_action_decline_integrity import (
    MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
)


def test_phase17n_boundary_checkpoint_is_owner_and_administrator_only() -> None:
    checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind="action_request",
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
    assert owner_event["payload"] == payload

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
