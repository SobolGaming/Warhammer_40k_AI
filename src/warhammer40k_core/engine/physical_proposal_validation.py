"""Pure physical-proposal ingress diagnostics shared by engine consumers.

Payload/context rejection is not a recorded rules attempt. It must not mutate
queues, decisions, RNG or the authoritative event history used by replay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalPayloadPayload,
    MovementProposalRequest,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState


def physical_proposal_invalid_status(
    *,
    state: GameState,
    result: DecisionResult,
    proposal_validation: ProposalValidationResult,
    message: str,
    phase_body_status: str | None = None,
) -> LifecycleStatus:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Physical proposal rejection requires a battle phase.")
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": phase.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": proposal_validation.status
                if phase_body_status is None
                else phase_body_status,
                "proposal_validation": proposal_validation.to_payload(),
            }
        ),
    )


def parse_movement_proposal_payload(
    *,
    proposal_request: MovementProposalRequest,
    payload: JsonValue,
) -> MovementProposalPayload | ProposalValidationResult:
    if not isinstance(payload, dict):
        return proposal_payload_parse_failure(
            proposal_request=proposal_request,
            error=GameLifecycleError("Movement proposal payload must be an object."),
            default_field="payload",
        )
    try:
        return MovementProposalPayload.from_payload(cast(MovementProposalPayloadPayload, payload))
    except (GameLifecycleError, GeometryError, KeyError, TypeError) as exc:
        return proposal_payload_parse_failure(
            proposal_request=proposal_request,
            error=exc,
            default_field="witness",
        )


def proposal_payload_parse_failure(
    *,
    proposal_request: MovementProposalRequest,
    error: GameLifecycleError | GeometryError | PlacementError | KeyError | TypeError,
    default_field: str,
) -> ProposalValidationResult:
    violation_code = "proposal_payload_malformed"
    field: str | None = default_field
    if type(error) is KeyError:
        missing = proposal_error_field(error)
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="proposal_payload_missing_field",
            message=f"Proposal payload missing required field: {missing}.",
            field=missing,
        )
    message = str(error)
    if "Unsupported ProposalKind token" in message:
        violation_code = "unsupported_proposal_kind"
        field = "proposal_kind"
    elif "proposal_kind" in message:
        field = "proposal_kind"
    elif "movement_mode" in message or "MovementMode" in message:
        field = "movement_mode"
    elif "fall_back_mode" in message or "FallBackModeKind" in message:
        field = "fall_back_mode"
    elif "witness" in message or "PathWitness" in message:
        field = "witness"
    elif "attempted_placement" in message or "UnitPlacement" in message:
        field = "attempted_placement"
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=f"Proposal payload is malformed: {message}",
        field=field,
    )


def proposal_error_field(error: KeyError) -> str:
    if len(error.args) != 1:
        return "payload"
    key = error.args[0]
    if type(key) is str and key.strip():
        return key.strip()
    return "payload"
