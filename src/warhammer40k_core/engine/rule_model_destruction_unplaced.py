from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule, model_by_id
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transports import (
    EMERGENCY_DISEMBARK_RULE_ID,
    DestroyedTransportDisembark,
    DisembarkModeKind,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.destroyed_transport_rules_unit_disembark import (
        DestroyedTransportRulesUnitDisembark,
    )
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
    _destroy_emergency_disembark_omitted_models(
        state=state,
        player_id=disembark.player_id,
        battle_round=disembark.battle_round,
        rules_unit_instance_id=disembark.unit_instance_id,
        component_unit_instance_ids=(disembark.unit_instance_id,),
        transport_unit_instance_id=disembark.transport_unit_instance_id,
        placed_model_instance_ids=tuple(
            sorted(
                placement.model_instance_id
                for placement in disembark.placement.selection.attempted_placement.model_placements
            )
        ),
        omitted_model_instance_ids=disembark.destroyed_model_instance_ids,
        requested_model_instance_ids=(model_instance_id,),
    )


def destroy_emergency_disembark_omitted_rules_unit_models(
    *,
    state: GameState,
    disembark: DestroyedTransportRulesUnitDisembark,
) -> None:
    """Logically destroy all omitted passengers after grouped validation succeeds."""

    from warhammer40k_core.engine.destroyed_transport_rules_unit_disembark import (
        DestroyedTransportRulesUnitDisembark,
    )
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Emergency Disembark destruction requires GameState.")
    if type(disembark) is not DestroyedTransportRulesUnitDisembark:
        raise GameLifecycleError(
            "Emergency Disembark destruction requires grouped destroyed Transport result."
        )
    if not disembark.is_valid:
        raise GameLifecycleError("Unplaced model destruction requires a valid disembark.")
    disembarked_state = disembark.placement.disembarked_unit_state
    if disembarked_state is None or disembarked_state.source_rule_id != EMERGENCY_DISEMBARK_RULE_ID:
        raise GameLifecycleError("Emergency Disembark destruction source drift.")
    selection = disembark.placement.selection
    _destroy_emergency_disembark_omitted_models(
        state=state,
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        rules_unit_instance_id=selection.unit_instance_id,
        component_unit_instance_ids=disembark.hazard_rolls.component_unit_instance_ids,
        transport_unit_instance_id=selection.transport_unit_instance_id,
        placed_model_instance_ids=tuple(
            sorted(
                placement.model_instance_id
                for placement in selection.attempted_placement.model_placements
            )
        ),
        omitted_model_instance_ids=disembark.destroyed_model_instance_ids,
        requested_model_instance_ids=disembark.destroyed_model_instance_ids,
    )


def _destroy_emergency_disembark_omitted_models(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
    transport_unit_instance_id: str,
    placed_model_instance_ids: tuple[str, ...],
    omitted_model_instance_ids: tuple[str, ...],
    requested_model_instance_ids: tuple[str, ...],
) -> None:
    requested_model_ids = tuple(
        _validate_identifier("model_instance_id", model_id)
        for model_id in requested_model_instance_ids
    )
    if state.battle_round != battle_round or player_id not in state.player_ids:
        raise GameLifecycleError("Emergency Disembark destruction context drift.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    )
    if rules_unit.owner_player_id != player_id or set(
        rules_unit.component_unit_instance_ids
    ) != set(component_unit_instance_ids):
        raise GameLifecycleError("Emergency Disembark destruction rules-unit drift.")
    omitted_model_ids = set(omitted_model_instance_ids)
    if not set(requested_model_ids).issubset(omitted_model_ids):
        raise GameLifecycleError("Model is not an omitted Emergency Disembark casualty.")
    placed_model_ids = set(placed_model_instance_ids)
    if placed_model_ids.intersection(requested_model_ids):
        raise GameLifecycleError("Emergency Disembark casualty cannot also be placed.")
    component_ids = set(component_unit_instance_ids)
    if any(
        state.unit_instance_id_for_model(model_id) not in component_ids
        for model_id in requested_model_ids
    ):
        raise GameLifecycleError("Emergency Disembark casualty unit drift.")
    cargo_state = state.transport_cargo_state_for_transport(transport_unit_instance_id)
    if (
        cargo_state is None
        or cargo_state.player_id != player_id
        or any(not cargo_state.contains_unit(component_id) for component_id in component_ids)
    ):
        raise GameLifecycleError("Emergency Disembark casualty lacks embarked authority.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Emergency Disembark destruction requires battlefield state.")
    if any(
        battlefield.model_placement_or_none(model_id) is not None
        for model_id in requested_model_ids
    ):
        raise GameLifecycleError("Emergency Disembark casualty must be unplaced.")
    if any(
        not model_by_id(state=state, model_instance_id=model_id).is_alive
        for model_id in requested_model_ids
    ):
        raise GameLifecycleError("Emergency Disembark casualty is already destroyed.")
    for requested_model_id in requested_model_ids:
        destroy_model_by_rule(
            state=state,
            model_instance_id=requested_model_id,
            remove_from_battlefield=False,
        )


_validate_identifier = IdentifierValidator(GameLifecycleError)
