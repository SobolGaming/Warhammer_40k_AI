from __future__ import annotations

from typing import TypedDict

from warhammer40k_core.engine.decision_request import (
    DecisionOptionPayload,
    DecisionRequest,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError


class DecisionRequestViewPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str | None
    payload: JsonValue
    options: list[DecisionOptionPayload]
    is_parameterized: bool


class GameViewPayload(TypedDict):
    viewer_player_id: str
    game_id: str
    stage: str
    battle_round: int
    active_player_id: str | None
    current_setup_step: str | None
    current_battle_phase: str | None
    player_ids: list[str]
    battlefield_state: JsonValue
    mission_setup: JsonValue
    public_secondary_mission_choices: list[JsonValue]
    public_secondary_mission_card_states: list[JsonValue]
    public_command_point_ledgers: list[JsonValue]
    public_victory_point_ledgers: list[JsonValue]
    public_stratagem_use_records: list[JsonValue]
    pending_decision: DecisionRequestViewPayload | None
    pending_proposal: JsonValue
    event_count: int


def project_game_view(
    *,
    lifecycle: GameLifecycle,
    viewer_player_id: str,
) -> GameViewPayload:
    if type(lifecycle) is not GameLifecycle:
        raise GameLifecycleError("Game projection requires a GameLifecycle.")
    state = lifecycle.state
    if state is None:
        raise GameLifecycleError("Game projection requires a started lifecycle.")
    viewer = _validate_viewer(state=state, viewer_player_id=viewer_player_id)
    pending_request = _pending_request(lifecycle)
    secondary_mission_choices_revealed = state.secondary_mission_choices_are_revealed()
    battlefield_payload = (
        None if state.battlefield_state is None else state.battlefield_state.to_payload()
    )
    mission_payload = None if state.mission_setup is None else state.mission_setup.to_payload()
    setup_step = state.current_setup_step
    battle_phase = state.current_battle_phase
    return {
        "viewer_player_id": viewer,
        "game_id": state.game_id,
        "stage": state.stage.value,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "current_setup_step": None if setup_step is None else setup_step.value,
        "current_battle_phase": None if battle_phase is None else battle_phase.value,
        "player_ids": list(state.player_ids),
        "battlefield_state": validate_json_value(battlefield_payload),
        "mission_setup": validate_json_value(mission_payload),
        "public_secondary_mission_choices": [
            validate_json_value(
                choice.to_public_payload(
                    viewer_player_id=viewer,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
            )
            for choice in state.secondary_mission_choices
        ],
        "public_secondary_mission_card_states": [
            validate_json_value(card_state_payload)
            for card_state_payload in state.public_secondary_mission_card_states(
                viewer_player_id=viewer
            )
        ],
        "public_command_point_ledgers": [
            validate_json_value(ledger.to_payload()) for ledger in state.command_point_ledgers
        ],
        "public_victory_point_ledgers": [
            validate_json_value(
                ledger.to_public_payload(
                    viewer_player_id=viewer,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
            )
            for ledger in state.victory_point_ledgers
        ],
        "public_stratagem_use_records": [
            validate_json_value(record.to_payload()) for record in state.stratagem_use_records
        ],
        "pending_decision": None
        if pending_request is None
        else _decision_request_view(pending_request, viewer_player_id=viewer),
        "pending_proposal": None
        if pending_request is None
        else _proposal_view(pending_request, viewer_player_id=viewer),
        "event_count": len(lifecycle.decision_controller.event_log.records),
    }


def _decision_request_view(
    request: DecisionRequest,
    *,
    viewer_player_id: str,
) -> DecisionRequestViewPayload:
    if _secret_request_hidden_from_viewer(request=request, viewer_player_id=viewer_player_id):
        return {
            "request_id": request.request_id,
            "decision_type": _redacted_decision_type(request.decision_type),
            "actor_id": request.actor_id,
            "payload": {
                "secret": True,
                "hidden": True,
            },
            "options": [],
            "is_parameterized": False,
        }
    return {
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
        "payload": request.payload,
        "options": [option.to_payload() for option in request.options],
        "is_parameterized": request.is_parameterized_submission_request(),
    }


def _proposal_view(
    request: DecisionRequest,
    *,
    viewer_player_id: str,
) -> JsonValue:
    if _secret_request_hidden_from_viewer(request=request, viewer_player_id=viewer_player_id):
        return None
    if not request.is_parameterized_submission_request():
        return None
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Parameterized DecisionRequest payload must be an object.")
    proposal_request = request.payload.get("proposal_request")
    if not isinstance(proposal_request, dict):
        raise GameLifecycleError("Parameterized DecisionRequest payload missing proposal_request.")
    return validate_json_value(_metadata_bearing_proposal_request(request, proposal_request))


def _metadata_bearing_proposal_request(
    request: DecisionRequest,
    proposal_request: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
    }
    for key, value in metadata.items():
        if key not in proposal_request:
            continue
        if proposal_request[key] != value:
            raise GameLifecycleError(
                "Parameterized proposal_request metadata must match DecisionRequest."
            )
    return {**metadata, **proposal_request}


def _pending_request(lifecycle: GameLifecycle) -> DecisionRequest | None:
    pending_requests = lifecycle.decision_controller.queue.pending_requests
    if not pending_requests:
        return None
    return pending_requests[0]


def _secret_request_hidden_from_viewer(
    *,
    request: DecisionRequest,
    viewer_player_id: str,
) -> bool:
    if request.actor_id == viewer_player_id:
        return False
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    secret = payload.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret DecisionRequest payload flag must be a bool.")
    return secret


def _redacted_decision_type(decision_type: str) -> str:
    if decision_type in {
        "draw_tactical_secondary_missions",
        "discard_tactical_secondary_mission",
        "start_mission_action",
    }:
        return "hidden_decision"
    return decision_type


def _validate_viewer(*, state: GameState, viewer_player_id: object) -> str:
    if type(viewer_player_id) is not str:
        raise GameLifecycleError("viewer_player_id must be a string.")
    viewer = viewer_player_id.strip()
    if not viewer:
        raise GameLifecycleError("viewer_player_id must not be empty.")
    if viewer not in state.player_ids:
        raise GameLifecycleError("viewer_player_id must be a player in this game.")
    return viewer
