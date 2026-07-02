from __future__ import annotations

import re
from typing import cast

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    FactionResourceStatus,
    faction_resource_spend_effect_payload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.source_backed_rerolls import (
    SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
    source_backed_reroll_permission_effect_payload,
    source_payload_from_reroll_effect_payload,
)

SOURCE_RULE_ID = "phase17f:phase17e:drukhari:army-rule"
DRUKHARI_FACTION_ID = "drukhari"
PAIN_TOKEN_RESOURCE_KIND = "drukhari_pain_token"
POWER_FROM_PAIN_EMPOWERED_EFFECT_KIND = "drukhari_power_from_pain_empowered"
POWER_FROM_PAIN_SPEND_REASON = "drukhari_power_from_pain_empowerment"
LITHE_AGILITY_ABILITY_KEY = "lithe_agility"
HATRED_ETERNAL_ABILITY_KEY = "hatred_eternal"
_PAIN_ABILITY_NAME_TO_KEY = {
    "lithe agility": LITHE_AGILITY_ABILITY_KEY,
    "hatred eternal": HATRED_ETERNAL_ABILITY_KEY,
}


def pain_tokens_available(state: object, *, player_id: str) -> int:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain token lookup requires GameState.")
    return state.faction_resource_total(
        player_id=_validate_identifier("player_id", player_id),
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
    )


def spend_pain_token(
    state: object,
    *,
    player_id: str,
    source_id: str,
) -> JsonValue:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain spend requires GameState.")
    result = state.spend_faction_resource(
        player_id=_validate_identifier("player_id", player_id),
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id=_validate_identifier("source_id", source_id),
    )
    if result.status is not FactionResourceStatus.APPLIED:
        raise GameLifecycleError("Power from Pain token spend failed.")
    return validate_json_value(result.to_payload())


def pain_token_spend_effect_payload() -> JsonValue:
    return faction_resource_spend_effect_payload(
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        reason=POWER_FROM_PAIN_SPEND_REASON,
    )


def power_from_pain_target_unit_ids(state: object, *, unit_instance_id: str) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain target lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )


def power_from_pain_empowerment_payload(
    *,
    unit_instance_id: str,
    target_unit_instance_ids: tuple[str, ...],
    trigger: str,
    phase: BattlePhaseKind,
    pain_ability_keys: tuple[str, ...],
    source_context: JsonValue,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": POWER_FROM_PAIN_EMPOWERED_EFFECT_KIND,
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "target_unit_instance_ids": list(
                _validate_identifier_tuple("target_unit_instance_ids", target_unit_instance_ids)
            ),
            "trigger": _validate_identifier("trigger", trigger),
            "phase": phase.value,
            "pain_ability_keys": list(_validate_pain_ability_keys(pain_ability_keys)),
            "source_context": validate_json_value(source_context),
        }
    )


def lithe_agility_advance_reroll_permission(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
) -> RerollPermission:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return RerollPermission(
        source_id=(
            f"{SOURCE_RULE_ID}:advance-reroll:"
            f"round-{_battle_round_for_state(state):02d}:{requested_unit_id}"
        ),
        timing_window="after_advance_roll",
        owning_player_id=_validate_identifier("player_id", player_id),
        eligible_roll_type="advance_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def lithe_agility_charge_reroll_permission(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
) -> RerollPermission:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return RerollPermission(
        source_id=(
            f"{SOURCE_RULE_ID}:charge-reroll:"
            f"round-{_battle_round_for_state(state):02d}:{requested_unit_id}"
        ),
        timing_window="after_charge_roll",
        owning_player_id=_validate_identifier("player_id", player_id),
        eligible_roll_type="charge_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def hatred_eternal_hit_reroll_permission(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
) -> RerollPermission:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return RerollPermission(
        source_id=(
            f"{SOURCE_RULE_ID}:hit-reroll:"
            f"round-{_battle_round_for_state(state):02d}:{requested_unit_id}"
        ),
        timing_window="attack_sequence.hit",
        owning_player_id=_validate_identifier("player_id", player_id),
        eligible_roll_type="attack_sequence.hit",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )


def power_from_pain_reroll_permission_effect_payload(
    *,
    unit_instance_id: str,
    target_unit_instance_ids: tuple[str, ...],
    trigger: str,
    phase: BattlePhaseKind,
    pain_ability_keys: tuple[str, ...],
    permission: RerollPermission,
    source_context: JsonValue,
) -> JsonValue:
    return source_backed_reroll_permission_effect_payload(
        target_unit_instance_ids=target_unit_instance_ids,
        permission=permission,
        source_payload=power_from_pain_empowerment_payload(
            unit_instance_id=unit_instance_id,
            target_unit_instance_ids=target_unit_instance_ids,
            trigger=trigger,
            phase=phase,
            pain_ability_keys=pain_ability_keys,
            source_context=source_context,
        ),
    )


def drukhari_rules_unit_can_empower_for_ability(
    state: object,
    *,
    player_id: str,
    unit_instance_id: str,
    pain_ability_key: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain eligibility requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_ability = _validate_pain_ability_key(pain_ability_key)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Power from Pain player army is missing.")
    if army.detachment_selection.faction_id != DRUKHARI_FACTION_ID:
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if rules_unit.owner_player_id != requested_player_id:
        raise GameLifecycleError("Power from Pain unit is not owned by the acting player.")
    if "DRUKHARI" not in {_canonical_keyword(keyword) for keyword in rules_unit.faction_keywords}:
        return False
    if requested_ability not in pain_ability_keys_for_rules_unit(
        state,
        unit_instance_id=requested_unit_id,
    ):
        return False
    return not unit_is_empowered_through_pain_for_ability(
        state,
        player_id=requested_player_id,
        unit_instance_id=requested_unit_id,
        pain_ability_key=requested_ability,
    )


def pain_ability_keys_for_rules_unit(
    state: object,
    *,
    unit_instance_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain ability lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    keys: list[str] = []
    seen: set[str] = set()
    for component in rules_unit.components:
        for ability in component.unit.datasheet_abilities:
            key = _pain_ability_key_for_name(ability.name)
            if key is None or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return tuple(keys)


def unit_is_empowered_through_pain_for_ability(
    state: object,
    *,
    player_id: str,
    unit_instance_id: str,
    pain_ability_key: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain empowerment lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_ability = _validate_pain_ability_key(pain_ability_key)
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Power from Pain empowerment payload is malformed.")
        source_payload = _power_from_pain_payload_from_effect_payload(payload)
        if source_payload is None:
            continue
        ability_keys = source_payload.get("pain_ability_keys")
        if not isinstance(ability_keys, list):
            raise GameLifecycleError("Power from Pain empowerment ability keys are malformed.")
        if requested_ability in {_validate_pain_ability_key(key) for key in tuple(ability_keys)}:
            return True
    return False


def _power_from_pain_payload_from_effect_payload(
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue] | None:
    if payload.get("effect_kind") == POWER_FROM_PAIN_EMPOWERED_EFFECT_KIND:
        return payload
    if payload.get("effect_kind") != SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND:
        return None
    source_payload = source_payload_from_reroll_effect_payload(payload)
    if source_payload.get("effect_kind") != POWER_FROM_PAIN_EMPOWERED_EFFECT_KIND:
        return None
    return source_payload


def _battle_round_for_state(state: object) -> int:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Power from Pain reroll permission requires GameState.")
    return state.battle_round


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_pain_ability_keys(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Power from Pain pain_ability_keys must be a tuple.")
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _validate_pain_ability_key(value)
        if key in seen:
            raise GameLifecycleError("Power from Pain pain_ability_keys must be unique.")
        seen.add(key)
        keys.append(key)
    if not keys:
        raise GameLifecycleError("Power from Pain pain_ability_keys must not be empty.")
    return tuple(keys)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Power from Pain {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for raw_value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(field_name, raw_value)
        if identifier in seen:
            raise GameLifecycleError(f"Power from Pain {field_name} must be unique.")
        seen.add(identifier)
        identifiers.append(identifier)
    if not identifiers:
        raise GameLifecycleError(f"Power from Pain {field_name} must not be empty.")
    return tuple(identifiers)


def _validate_pain_ability_key(value: object) -> str:
    key = _validate_identifier("pain_ability_key", value)
    if key not in {LITHE_AGILITY_ABILITY_KEY, HATRED_ETERNAL_ABILITY_KEY}:
        raise GameLifecycleError("Power from Pain pain ability is unsupported.")
    return key


def _pain_ability_key_for_name(name: str) -> str | None:
    normalized = _normalize_pain_ability_name(name)
    if not normalized:
        return None
    return _PAIN_ABILITY_NAME_TO_KEY.get(normalized)


def _normalize_pain_ability_name(name: object) -> str:
    if type(name) is not str:
        raise GameLifecycleError("Power from Pain ability name must be a string.")
    normalized = re.sub(r"\(pain\)", "", name.strip().lower())
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).upper().replace(" ", "_")
