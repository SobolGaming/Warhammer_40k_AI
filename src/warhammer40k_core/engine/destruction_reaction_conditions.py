from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.damage_allocation import DamageApplication
from warhammer40k_core.engine.destruction_provenance import (
    DestructionAttackKind,
    DestructionProvenance,
    DestructionSourceKind,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def optional_destruction_reaction_trigger_conditions_met(
    *,
    state: GameState,
    destruction_provenance: DestructionProvenance,
    damage: DamageApplication,
    descriptor: dict[str, JsonValue],
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Destruction reaction condition requires GameState.")
    if type(destruction_provenance) is not DestructionProvenance:
        raise GameLifecycleError("Destruction reaction condition requires provenance.")
    if type(damage) is not DamageApplication:
        raise GameLifecycleError("Destruction reaction condition requires damage.")
    if not optional_destruction_reaction_trigger_battle_round_is_current(
        state=state,
        descriptor=descriptor,
    ):
        return False
    if not optional_destruction_reaction_active_effect_requirement_is_met(
        state=state,
        descriptor=descriptor,
    ):
        return False
    if descriptor.get("requires_destroyed_by_melee_attack") is True and not (
        destruction_provenance.destruction_source_kind is DestructionSourceKind.ATTACK
        and destruction_provenance.attack_kind is DestructionAttackKind.MELEE
    ):
        return False
    if descriptor.get("requires_not_fought_this_phase") is True:
        fight_state = state.fight_phase_state
        if (
            fight_state is not None
            and damage.target_unit_instance_id
            in fight_state.fight_order_state.selected_to_fight_unit_ids
        ):
            return False
    return True


def optional_destruction_reaction_trigger_battle_round_is_current(
    *,
    state: GameState,
    descriptor: dict[str, JsonValue],
) -> bool:
    if "battle_round" not in descriptor:
        return True
    return _positive_int(descriptor, key="battle_round") == state.battle_round


def optional_destruction_reaction_active_effect_requirement_is_met(
    *,
    state: GameState,
    descriptor: dict[str, JsonValue],
) -> bool:
    raw_requirement = descriptor.get("requires_active_persisting_effect")
    if raw_requirement is None:
        return True
    requirement = _object(raw_requirement)
    required_owner_id = _optional_string(requirement, key="owner_player_id")
    required_source_rule_id = _optional_string(requirement, key="source_rule_id")
    required_effect_kind = _optional_string(requirement, key="effect_kind")
    required_target_unit_id = _optional_string(requirement, key="target_unit_instance_id")
    required_battle_round = (
        _positive_int(requirement, key="battle_round") if "battle_round" in requirement else None
    )
    required_selected_id = _optional_string(requirement, key="selected_blessing_id")
    for effect in state.persisting_effects:
        if required_owner_id is not None and effect.owner_player_id != required_owner_id:
            continue
        if required_source_rule_id is not None and effect.source_rule_id != required_source_rule_id:
            continue
        if required_target_unit_id is not None and not effect.applies_to_unit(
            required_target_unit_id
        ):
            continue
        payload = _object(effect.effect_payload)
        if required_effect_kind is not None and payload.get("effect_kind") != required_effect_kind:
            continue
        if required_battle_round is not None and payload.get("battle_round") != (
            required_battle_round
        ):
            continue
        if required_selected_id is not None and required_selected_id not in _string_list(
            payload,
            key="selected_blessing_ids",
        ):
            continue
        return True
    return False


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Destruction reaction payload value must be an object.")
    return value


def _optional_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Destruction reaction {key} must be a non-empty string.")
    return value


def _positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"Destruction reaction {key} must be a positive integer.")
    return value


def _string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(type(item) is str and item for item in value):
        raise GameLifecycleError(f"Destruction reaction {key} must be a string list.")
    return tuple(cast(str, item) for item in value)
