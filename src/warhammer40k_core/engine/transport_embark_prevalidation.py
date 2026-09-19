"""Revalidate an offered embark before accepting its finite decision."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import SELECT_EMBARK_TRANSPORT_DECISION_TYPE
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transport_embark_validation import embark_after_setup_forbidden
from warhammer40k_core.engine.transports import EmbarkSelection, EmbarkSelectionPayload


def invalid_embark_setup(
    *, state: GameState, request: DecisionRequest, result: DecisionResult
) -> LifecycleStatus | None:
    if request.decision_type != SELECT_EMBARK_TRANSPORT_DECISION_TYPE:
        return None
    result.validate_for_request(request)
    payload = result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Embark selection requires an object.")
    if payload.get("transport_decision") != "embark_unit":
        return None
    selection = EmbarkSelection.from_payload(cast(EmbarkSelectionPayload, payload))
    if state.active_player_id is None:
        raise GameLifecycleError("Embark requires the current turn owner.")
    if selection.battle_round != state.battle_round or embark_after_setup_forbidden(
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=selection.unit_instance_id),
        movement_history=tuple(state.phase_movement_history),
        turn_player_id=state.active_player_id,
        selection=selection,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Embark setup-turn eligibility changed.",
            payload={"invalid_reason": "embark_after_setup_forbidden"},
        )
    return None
