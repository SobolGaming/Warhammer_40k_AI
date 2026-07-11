from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.stratagems_model import (
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemUseRecord,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND = "selected_friendly_companion_unit"
CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND = "controlled_objective_marker"
COMPANION_UNIT_CONTEXT_KEY = "companion_unit_instance_id"
OBJECTIVE_MARKER_CONTEXT_KEY = "objective_marker_id"
COMPANION_OPTIONAL_KEY = "companion_optional"
COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY = (
    "companion_forbidden_if_within_engagement_range"
)
COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY = "companion_required_contextual_status"
COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY = "companion_required_keywords_by_target_keyword"
COMPANION_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY = (
    "companion_required_reinforcement_arrival_this_turn"
)
EFFECT_SELECTION_KIND_KEY = "effect_selection_kind"
TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY = "target_required_contextual_status"
TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS = (
    "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos"
)
TARGET_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY = (
    "target_required_reinforcement_arrival_this_turn"
)
TARGET_REQUIRED_TRIGGER_CONTEXT_LIST_KEY = "target_required_trigger_context_list_key"
REQUIRED_TRIGGER_CONTEXT_KEYS_KEY = "required_trigger_context_keys"
REQUIRED_NON_EMPTY_TRIGGER_CONTEXT_KEYS_KEY = "required_non_empty_trigger_context_keys"

_validate_identifier = IdentifierValidator(GameLifecycleError)


def companion_unit_effect_selection(unit_instance_id: str) -> JsonValue:
    return {
        EFFECT_SELECTION_KIND_KEY: SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
        COMPANION_UNIT_CONTEXT_KEY: _validate_identifier(
            COMPANION_UNIT_CONTEXT_KEY,
            unit_instance_id,
        ),
    }


def companion_unit_id_or_none(effect_selection: JsonValue) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    if (
        effect_selection.get(EFFECT_SELECTION_KIND_KEY)
        != SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND
    ):
        return None
    value = effect_selection.get(COMPANION_UNIT_CONTEXT_KEY)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError("Companion unit effect selection must contain a unit ID.")
    return _validate_identifier(COMPANION_UNIT_CONTEXT_KEY, value)


def objective_marker_effect_selection(objective_marker_id: str) -> JsonValue:
    return {
        EFFECT_SELECTION_KIND_KEY: CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND,
        OBJECTIVE_MARKER_CONTEXT_KEY: _validate_identifier(
            OBJECTIVE_MARKER_CONTEXT_KEY,
            objective_marker_id,
        ),
    }


def objective_marker_id_or_none(effect_selection: JsonValue) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    if (
        effect_selection.get(EFFECT_SELECTION_KIND_KEY)
        != CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND
    ):
        return None
    value = effect_selection.get(OBJECTIVE_MARKER_CONTEXT_KEY)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError("Objective marker effect selection must contain a marker ID.")
    return _validate_identifier(OBJECTIVE_MARKER_CONTEXT_KEY, value)


def generic_rule_ir_execution_target_unit_ids(use_record: StratagemUseRecord) -> tuple[str, ...]:
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic RuleIR target IDs require a StratagemUseRecord.")
    target_ids = list(use_record.targeted_unit_instance_ids)
    companion_id = companion_unit_id_or_none(use_record.effect_selection)
    if companion_id is not None and companion_id not in target_ids:
        target_ids.append(companion_id)
    return tuple(sorted(target_ids))


def companion_effect_selections_for_binding(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> tuple[JsonValue, ...]:
    if type(definition) is not StratagemDefinition:
        raise GameLifecycleError("Companion selection requires a StratagemDefinition.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Companion selection requires a StratagemEligibilityContext.")
    target_unit_id = target_binding.target_unit_instance_id
    if target_unit_id is None:
        raise GameLifecycleError("Companion selection requires a target unit.")
    payload = _payload_object(definition.effect_payload)
    selections: list[JsonValue] = []
    if _payload_bool_or_false(payload, COMPANION_OPTIONAL_KEY):
        selections.append(None)
    target_unit = unit_by_id(state=state, unit_instance_id=target_unit_id)
    for unit in friendly_units(state=state, player_id=context.player_id):
        if unit.unit_instance_id == target_unit_id:
            continue
        if not companion_keywords_match(
            payload=payload,
            target_unit=target_unit,
            companion_unit=unit,
        ):
            continue
        if _payload_bool_or_false(
            payload,
            COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY,
        ):
            from warhammer40k_core.engine.stratagems_geometry import (
                _unit_is_within_enemy_engagement_range,
            )

            if _unit_is_within_enemy_engagement_range(
                state=state,
                player_id=context.player_id,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
        companion_status = _payload_optional_string(
            payload,
            COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY,
        )
        if companion_status is not None and not unit_has_contextual_status(
            state=state,
            player_id=context.player_id,
            unit_instance_id=unit.unit_instance_id,
            status=companion_status,
        ):
            continue
        selections.append(companion_unit_effect_selection(unit.unit_instance_id))
    return tuple(selections)


def controlled_objective_effect_selections_for_binding(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> tuple[JsonValue, ...]:
    from warhammer40k_core.engine.stratagems_targeting import (
        _controlled_objective_marker_ids_for_target,
    )

    return tuple(
        objective_marker_effect_selection(objective_id)
        for objective_id in _controlled_objective_marker_ids_for_target(
            state=state,
            player_id=context.player_id,
            context=context,
            target_binding=target_binding,
            ruleset_descriptor=None,
        )
    )


def companion_selection_error(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue,
) -> str | None:
    payload = _payload_object(definition.effect_payload)
    companion_id = companion_unit_id_or_none(effect_selection)
    if companion_id is None:
        if _payload_bool_or_false(payload, COMPANION_OPTIONAL_KEY):
            return None
        return f"{COMPANION_UNIT_CONTEXT_KEY}_required"
    if target_binding is None or target_binding.target_unit_instance_id is None:
        return "target_unit_required"
    target_unit_id = target_binding.target_unit_instance_id
    if companion_id == target_unit_id:
        return "companion_unit_is_target"
    companion = unit_by_id(state=state, unit_instance_id=companion_id)
    if unit_owner_player_id(state=state, unit_instance_id=companion_id) != context.player_id:
        return "companion_unit_not_friendly"
    if _payload_bool_or_false(
        payload,
        COMPANION_REQUIRED_REINFORCEMENT_ARRIVAL_THIS_TURN_KEY,
    ) and not unit_arrived_from_reserves_this_turn(state=state, unit_instance_id=companion_id):
        return "companion_unit_not_arrived_from_reserves_this_turn"
    if _payload_bool_or_false(payload, COMPANION_FORBIDDEN_IF_WITHIN_ENGAGEMENT_RANGE_KEY):
        from warhammer40k_core.engine.stratagems_geometry import (
            _unit_is_within_enemy_engagement_range,
        )

        if _unit_is_within_enemy_engagement_range(
            state=state,
            player_id=context.player_id,
            unit_instance_id=companion_id,
        ):
            return "companion_unit_within_engagement_range"
    companion_status = _payload_optional_string(payload, COMPANION_REQUIRED_CONTEXTUAL_STATUS_KEY)
    if companion_status is not None and not unit_has_contextual_status(
        state=state,
        player_id=context.player_id,
        unit_instance_id=companion_id,
        status=companion_status,
    ):
        return "companion_unit_missing_contextual_status"
    target_unit = unit_by_id(state=state, unit_instance_id=target_unit_id)
    if not companion_keywords_match(
        payload=payload,
        target_unit=target_unit,
        companion_unit=companion,
    ):
        return "companion_unit_keyword_mismatch"
    return None


def objective_selection_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue,
) -> str | None:
    if target_binding is None or target_binding.target_unit_instance_id is None:
        return "target_unit_required"
    objective_id = objective_marker_id_or_none(effect_selection)
    if objective_id is None:
        return f"{OBJECTIVE_MARKER_CONTEXT_KEY}_required"
    eligible_objective_ids = {
        _validate_identifier(OBJECTIVE_MARKER_CONTEXT_KEY, eligible_id)
        for eligible_id in controlled_objective_effect_selection_ids_for_binding(
            state=state,
            context=context,
            target_binding=target_binding,
        )
    }
    if not eligible_objective_ids:
        return "no_controlled_objective_marker"
    if objective_id not in eligible_objective_ids:
        return "objective_marker_not_controlled_by_target_unit"
    return None


def controlled_objective_effect_selection_ids_for_binding(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.stratagems_targeting import (
        _controlled_objective_marker_ids_for_target,
    )

    return _controlled_objective_marker_ids_for_target(
        state=state,
        player_id=context.player_id,
        context=context,
        target_binding=target_binding,
        ruleset_descriptor=None,
    )


def unit_has_contextual_status(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    status: str,
) -> bool:
    contextual_status = _payload_string(TARGET_REQUIRED_CONTEXTUAL_STATUS_KEY, status)
    if contextual_status == TARGET_CONTEXTUAL_STATUS_SHADOW_OF_CHAOS:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
            army_rule,
        )

        return army_rule.unit_within_shadow_of_chaos(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
        )
    raise GameLifecycleError(f"Unsupported contextual status: {contextual_status}.")


def companion_keywords_match(
    *,
    payload: dict[str, JsonValue],
    target_unit: UnitInstance,
    companion_unit: UnitInstance,
) -> bool:
    mapping = payload.get(COMPANION_REQUIRED_KEYWORDS_BY_TARGET_KEYWORD_KEY)
    if mapping is None:
        return True
    if not isinstance(mapping, dict):
        raise GameLifecycleError("Companion keyword mapping must be an object.")
    required_keywords: set[str] = set()
    target_keywords = unit_keyword_set(target_unit)
    for raw_target_keyword, raw_companion_keywords in mapping.items():
        if type(raw_target_keyword) is not str:
            raise GameLifecycleError("Companion keyword map keys must be strings.")
        if _canonical_keyword(raw_target_keyword) not in target_keywords:
            continue
        if not isinstance(raw_companion_keywords, list):
            raise GameLifecycleError("Companion keyword map values must be lists.")
        for raw_companion_keyword in raw_companion_keywords:
            if type(raw_companion_keyword) is not str:
                raise GameLifecycleError("Companion keyword map values must contain strings.")
            required_keywords.add(_canonical_keyword(raw_companion_keyword))
    if not required_keywords:
        return False
    return bool(required_keywords & unit_keyword_set(companion_unit))


def unit_arrived_from_reserves_this_turn(*, state: GameState, unit_instance_id: str) -> bool:
    reserve_state = state.reserve_state_for_unit(unit_instance_id)
    if reserve_state is None:
        return False
    return (
        reserve_state.status is ReserveStatus.ARRIVED
        and reserve_state.arrived_battle_round == state.battle_round
    )


def unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Generic stratagem metadata unit is unknown.")


def friendly_units(*, state: GameState, player_id: str) -> tuple[UnitInstance, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return tuple(army.units)
    raise GameLifecycleError("Generic stratagem metadata player has no army.")


def unit_owner_player_id(*, state: GameState, unit_instance_id: str) -> str:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        if any(unit.unit_instance_id == requested_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Generic stratagem metadata unit owner is unknown.")


def unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic stratagem metadata keyword lookup requires a unit.")
    return _canonical_keyword(keyword) in unit_keyword_set(unit)


def unit_keyword_set(unit: UnitInstance) -> set[str]:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic stratagem metadata keyword set requires a unit.")
    return {_canonical_keyword(keyword) for keyword in (*unit.keywords, *unit.faction_keywords)}


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Generic stratagem metadata payload must be an object.")
    return value


def _payload_bool_or_false(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if value is None:
        return False
    if type(value) is not bool:
        raise GameLifecycleError(f"{key} must be a bool.")
    return value


def _payload_optional_string(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _payload_string(key, value)


def _payload_string(key: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    if not value.strip():
        raise GameLifecycleError(f"{key} must not be empty.")
    return value.strip()


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str:
        raise GameLifecycleError("Keyword must be a string.")
    return keyword.strip().upper().replace("_", " ").replace("-", " ")
