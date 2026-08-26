from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule, model_by_id
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transports import (
    EMERGENCY_DISEMBARK_RULE_ID,
    DestroyedTransportDisembark,
    DisembarkModeKind,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def destroy_emergency_disembark_omitted_model(
    *,
    state: GameState,
    disembark: DestroyedTransportDisembark,
    model_instance_id: str,
) -> None:
    """Logically destroy one passenger omitted from a valid Emergency Disembark."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Emergency Disembark destruction requires GameState.")
    if type(disembark) is not DestroyedTransportDisembark:
        raise GameLifecycleError(
            "Emergency Disembark destruction requires DestroyedTransportDisembark."
        )
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    if disembark.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
        raise GameLifecycleError("Unplaced model destruction requires Emergency Disembark.")
    if not disembark.placement.is_valid:
        raise GameLifecycleError("Unplaced model destruction requires a valid disembark.")
    disembarked_state = disembark.disembarked_unit_state
    if disembarked_state is None or disembarked_state.source_rule_id != EMERGENCY_DISEMBARK_RULE_ID:
        raise GameLifecycleError("Emergency Disembark destruction source drift.")
    if (
        state.battle_round != disembark.battle_round
        or disembark.player_id not in state.player_ids
        or disembarked_state.player_id != disembark.player_id
        or disembarked_state.unit_instance_id != disembark.unit_instance_id
        or disembarked_state.transport_unit_instance_id != disembark.transport_unit_instance_id
    ):
        raise GameLifecycleError("Emergency Disembark destruction context drift.")
    if requested_model_id not in disembark.destroyed_model_instance_ids:
        raise GameLifecycleError("Model is not an omitted Emergency Disembark casualty.")
    placed_model_ids = {
        placement.model_instance_id
        for placement in disembark.placement.selection.attempted_placement.model_placements
    }
    if requested_model_id in placed_model_ids:
        raise GameLifecycleError("Emergency Disembark casualty cannot also be placed.")
    if state.unit_instance_id_for_model(requested_model_id) != disembark.unit_instance_id:
        raise GameLifecycleError("Emergency Disembark casualty unit drift.")
    cargo_state = state.transport_cargo_state_for_transport(disembark.transport_unit_instance_id)
    if (
        cargo_state is None
        or cargo_state.player_id != disembark.player_id
        or not cargo_state.contains_unit(disembark.unit_instance_id)
    ):
        raise GameLifecycleError("Emergency Disembark casualty lacks embarked authority.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Emergency Disembark destruction requires battlefield state.")
    if battlefield.model_placement_or_none(requested_model_id) is not None:
        raise GameLifecycleError("Emergency Disembark casualty must be unplaced.")
    if not model_by_id(state=state, model_instance_id=requested_model_id).is_alive:
        raise GameLifecycleError("Emergency Disembark casualty is already destroyed.")
    destroy_model_by_rule(
        state=state,
        model_instance_id=requested_model_id,
        remove_from_battlefield=False,
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
