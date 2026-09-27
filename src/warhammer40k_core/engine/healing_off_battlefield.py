"""Source-preserving non-spatial revival for cargo and unarrived reserves."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.damage_allocation import model_by_id, unit_by_id
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing_source_context import revival_wounds_remaining
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transport_cargo_membership import reserve_state_with_updated_cargo
from warhammer40k_core.engine.transports import TransportCargoState

if TYPE_CHECKING:
    from warhammer40k_core.engine.healing import HealingEffect, HealingStep


def revival_location(*, state: GameState, unit_instance_id: str) -> JsonValue:
    """Bind every physical component to an explicit, consistent location owner."""
    target = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    cargo = tuple(
        state.transport_cargo_state_for_embarked_unit(i)
        for i in target.component_unit_instance_ids
        if any(model.is_alive for model in unit_by_id(state=state, unit_instance_id=i).own_models)
    )
    reserve = state.reserve_state_for_unit(target.unit_instance_id)
    if any(row is not None for row in cargo):
        carrier = cargo[0]
        if carrier is None or any(row != carrier for row in cargo):
            raise GameLifecycleError("Revival has incomplete embarked component authority.")
        transport = unit_by_id(state=state, unit_instance_id=carrier.transport_unit_instance_id)
        if not any(model.is_alive for model in transport.own_models):
            raise GameLifecycleError("Revival cannot use a destroyed Transport.")
        if reserve is not None and reserve.status is ReserveStatus.IN_RESERVES:
            raise GameLifecycleError("Revival has conflicting cargo and reserve authority.")
        location = validate_json_value(
            {
                "kind": "embarked",
                "cargo_state": carrier.to_payload(),
                "occupied_model_count": _cargo_model_count(state, carrier),
                "battle_round": state.battle_round,
                "turn_owner_player_id": state.active_player_id,
                "phase": None
                if state.current_battle_phase is None
                else state.current_battle_phase.value,
            }
        )
    elif reserve is not None and reserve.status is ReserveStatus.IN_RESERVES:
        location = validate_json_value(
            {
                "kind": "reserves",
                "reserve_state": reserve.to_payload(),
                "battle_round": state.battle_round,
                "turn_owner_player_id": state.active_player_id,
                "phase": None
                if state.current_battle_phase is None
                else state.current_battle_phase.value,
            }
        )
    else:
        return None
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Off-battlefield revival requires battlefield state.")
    if {model.model_instance_id for model in target.own_models} & set(
        battlefield.placed_model_ids()
    ):
        raise GameLifecycleError("Off-battlefield revival has placed models.")
    return location


def apply_off_battlefield_revival(
    *,
    state: GameState,
    effect: HealingEffect,
    model_instance_id: str,
    request_id: str | None,
    result_id: str | None,
) -> HealingStep | None:
    from warhammer40k_core.engine.healing import (
        HealingStep,
        HealingStepKind,
        healing_army_definitions_with_model_wounds,
    )

    location = revival_location(state=state, unit_instance_id=effect.target_unit_instance_id)
    if location is None:
        return None
    if request_id is None or result_id is None:
        raise GameLifecycleError("Off-battlefield revival requires recorded selection provenance.")
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if model.is_alive:
        raise GameLifecycleError("Off-battlefield revival requires a destroyed model.")
    from warhammer40k_core.engine.transports import TransportCargoStatePayload

    if not isinstance(location, dict):
        raise GameLifecycleError("Off-battlefield revival location must be an object.")
    cargo = (
        TransportCargoState.from_payload(cast(TransportCargoStatePayload, location["cargo_state"]))
        if location["kind"] == "embarked"
        else None
    )
    if cargo is not None:
        count = _cargo_model_count(state, cargo)
        if count >= cargo.capacity_profile.max_model_count:
            return HealingStep(
                step_index=effect.next_step_index(),
                step_kind=HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY,
                model_instance_id=model_instance_id,
                starting_wounds_remaining=0,
                final_wounds_remaining=0,
                request_id=request_id,
                result_id=result_id,
            )
    final_wounds = revival_wounds_remaining(effect.source_context, model.initial_wounds)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Off-battlefield revival requires battlefield state.")
    # Validate both replacements before either authoritative mutation.
    returned_battlefield = battlefield.with_returned_unplaced_model(model_instance_id)
    returned_armies = healing_army_definitions_with_model_wounds(
        armies=tuple(state.army_definitions),
        model_instance_id=model_instance_id,
        wounds_remaining=final_wounds,
    )
    returned_cargo = cargo
    returned_reserve = None
    if cargo is not None:
        component_id = state.unit_instance_id_for_model(model_instance_id)
        if component_id not in cargo.embarked_unit_instance_ids:
            returned_cargo = cargo.with_embarked_unit(component_id)
        assert returned_cargo is not None
        returned_reserve = reserve_state_with_updated_cargo(
            state=state, before=cargo, after=returned_cargo
        )
    state.army_definitions[:] = returned_armies
    state.replace_battlefield_state(returned_battlefield)
    if returned_cargo is not None:
        state.replace_transport_cargo_state(returned_cargo)
    if returned_reserve is not None:
        state.replace_reserve_state(returned_reserve)
    return HealingStep(
        step_index=effect.next_step_index(),
        step_kind=HealingStepKind.REVIVE_MODEL_EMBARKED
        if cargo is not None
        else HealingStepKind.REVIVE_MODEL_IN_RESERVES,
        model_instance_id=model_instance_id,
        starting_wounds_remaining=0,
        final_wounds_remaining=final_wounds,
        request_id=request_id,
        result_id=result_id,
    )


def validate_off_battlefield_step(
    *,
    state: GameState,
    request: DecisionRequest,
    step: HealingStep,
) -> None:
    """Authenticate source wounds and non-spatial location from the accepted request."""
    from warhammer40k_core.engine.healing import HealingStepKind, healing_effect_from_request
    from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload
    from warhammer40k_core.engine.transports import TransportCargoState, TransportCargoStatePayload

    effect = healing_effect_from_request(request=request)
    if step.model_instance_id is None or not isinstance(request.payload, dict):
        raise GameLifecycleError("Off-battlefield revival lacks model/request authority.")
    location = request.payload.get("revival_location")
    if not isinstance(location, dict):
        raise GameLifecycleError("Off-battlefield revival lacks location authority.")
    model = model_by_id(state=state, model_instance_id=step.model_instance_id)
    if step.step_kind is HealingStepKind.REVIVE_MODEL_IN_RESERVES:
        if (
            set(location)
            != {"kind", "reserve_state", "battle_round", "turn_owner_player_id", "phase"}
            or location["kind"] != "reserves"
        ):
            raise GameLifecycleError("Reserve revival location drifted.")
        raw = location["reserve_state"]
        if not isinstance(raw, dict):
            raise GameLifecycleError("Reserve revival state is invalid.")
        reserve = ReserveState.from_payload(cast(ReserveStatePayload, raw))
        if (
            reserve.unit_instance_id != effect.target_unit_instance_id
            or reserve.status is not ReserveStatus.IN_RESERVES
        ):
            raise GameLifecycleError("Reserve revival owner/status drifted.")
    else:
        if (
            set(location)
            != {
                "kind",
                "cargo_state",
                "occupied_model_count",
                "battle_round",
                "turn_owner_player_id",
                "phase",
            }
            or location["kind"] != "embarked"
        ):
            raise GameLifecycleError("Embarked revival location drifted.")
        raw = location["cargo_state"]
        if not isinstance(raw, dict):
            raise GameLifecycleError("Embarked revival state is invalid.")
        cargo = TransportCargoState.from_payload(cast(TransportCargoStatePayload, raw))
        target = rules_unit_view_by_id(state=state, unit_instance_id=effect.target_unit_instance_id)
        if state.unit_instance_id_for_model(
            step.model_instance_id
        ) not in target.component_unit_instance_ids or not set(
            target.component_unit_instance_ids
        ) & set(cargo.embarked_unit_instance_ids):
            raise GameLifecycleError("Embarked revival component drifted.")
        count = location["occupied_model_count"]
        if type(count) is not int or count < 0:
            raise GameLifecycleError("Embarked revival capacity evidence is invalid.")
        if (count >= cargo.capacity_profile.max_model_count) != (
            step.step_kind is HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY
        ):
            raise GameLifecycleError("Embarked revival capacity outcome drifted.")

    expected = (
        0
        if step.step_kind is HealingStepKind.REVIVE_MODEL_DESTROYED_NO_CAPACITY
        else revival_wounds_remaining(effect.source_context, model.initial_wounds)
    )
    if step.starting_wounds_remaining != 0 or step.final_wounds_remaining != expected:
        raise GameLifecycleError("Off-battlefield revival source wounds drifted.")
    if step.transition_batch is not None:
        raise GameLifecycleError("Off-battlefield revival must remain unplaced.")


def _cargo_model_count(state: GameState, cargo: TransportCargoState) -> int:
    return sum(
        model.is_alive
        for unit_id in cargo.embarked_unit_instance_ids
        for model in unit_by_id(state=state, unit_instance_id=unit_id).own_models
    )
