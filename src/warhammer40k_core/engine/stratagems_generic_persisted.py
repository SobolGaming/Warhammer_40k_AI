from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.charge_effects import CHARGE_AFTER_ADVANCE_EFFECT_KIND
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState
from warhammer40k_core.engine.stratagems_generic_metadata import objective_marker_id_or_none
from warhammer40k_core.engine.stratagems_model import (
    StratagemEligibilityContext,
    StratagemUseRecord,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rule_execution import RuleExecutionResult

_validate_identifier = IdentifierValidator(GameLifecycleError)


def record_generic_charge_after_advance_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    unit_id = _single_target_unit_id(use_record)
    source_effect_kind = _optional_rule_effect_string_parameter(
        effect_payload,
        "source_effect_kind",
    )
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:charge-after-advance:{unit_id}",
        source_rule_id=_rule_effect_source_id(effect_payload),
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=_expiration_for_rule_effect_payload(
            effect_payload=effect_payload,
            context=context,
            use_record=use_record,
        ),
        effect_payload={
            "effect_kind": CHARGE_AFTER_ADVANCE_EFFECT_KIND,
            "source_effect_kind": source_effect_kind,
            "stratagem_id": use_record.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "generic_stratagem_charge_after_advance_registered",
        _runtime_effect_event_payload(
            state=state,
            context=context,
            use_record=use_record,
            effect=effect,
        ),
    )


def record_generic_sticky_objective_control_state(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    rule_result: RuleExecutionResult,
    effect_payload: dict[str, JsonValue],
) -> None:
    if context.active_player_id is None:
        raise GameLifecycleError("Generic sticky objective control requires active player.")
    if (
        _required_rule_effect_string_parameter(effect_payload, "objective_selection")
        != "selected_controlled_objective_marker"
    ):
        raise GameLifecycleError("Generic sticky objective control requires objective selection.")
    objective_id = objective_marker_id_or_none(use_record.effect_selection)
    if objective_id is None:
        raise GameLifecycleError("Generic sticky objective control requires objective selection.")
    target_unit_id = _single_target_unit_id(use_record)
    sticky_state = StickyObjectiveControlState(
        state_id=f"{use_record.use_id}:sticky-objective:{objective_id}",
        game_id=state.game_id,
        player_id=use_record.player_id,
        objective_id=objective_id,
        source_rule_id=_rule_effect_source_id(effect_payload),
        source_event_id=use_record.use_id,
        battle_round=use_record.battle_round,
        phase=use_record.phase.value,
        active_player_id=context.active_player_id,
        originating_unit_instance_id=target_unit_id,
        destroyed_unit_instance_id=target_unit_id,
        replay_payload={
            "effect_kind": _required_rule_effect_string_parameter(
                effect_payload,
                "sticky_effect_kind",
            ),
            "stratagem_id": use_record.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "target_unit_instance_id": target_unit_id,
            "objective_id": objective_id,
            "shadow_of_chaos_aura_inches": _required_rule_effect_number_parameter(
                effect_payload,
                "shadow_of_chaos_aura_inches",
            ),
            "generic_rule_execution_result": validate_json_value(rule_result.to_payload()),
            "generic_rule_effect": validate_json_value(effect_payload),
        },
    )
    state.record_sticky_objective_control_state(sticky_state)
    decisions.event_log.append(
        "generic_stratagem_sticky_objective_control_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "active_player_id": context.active_player_id,
            "stratagem_use": validate_json_value(use_record.to_payload()),
            "sticky_objective_control_state": validate_json_value(sticky_state.to_payload()),
        },
    )


def _single_target_unit_id(use_record: StratagemUseRecord) -> str:
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic Stratagem source binding requires use record.")
    if len(use_record.targeted_unit_instance_ids) != 1:
        raise GameLifecycleError("Generic Stratagem effect requires one target unit.")
    return use_record.targeted_unit_instance_ids[0]


def _rule_effect_parameter(effect_payload: dict[str, JsonValue], key: str) -> JsonValue:
    requested_key = _validate_identifier("generic Stratagem effect parameter", key)
    effect = effect_payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic Stratagem effect payload requires effect object.")
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic Stratagem effect parameters must be a list.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Generic Stratagem effect parameter must be an object.")
        if parameter.get("key") == requested_key:
            return validate_json_value(parameter.get("value"))
    return None


def _rule_effect_source_id(effect_payload: dict[str, JsonValue]) -> str:
    value = effect_payload.get("source_id")
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem effect payload requires source_id.")
    return _validate_identifier("generic Stratagem source_id", value)


def _expiration_for_rule_effect_payload(
    *,
    effect_payload: dict[str, JsonValue],
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
) -> EffectExpiration:
    duration = effect_payload.get("duration")
    if not isinstance(duration, dict):
        raise GameLifecycleError("Generic persisted Stratagem effect requires duration.")
    kind = duration.get("kind")
    if kind == "permanent":
        return EffectExpiration.end_of_battle()
    if kind != "until_timing_endpoint":
        raise GameLifecycleError("Generic persisted Stratagem effect duration is unsupported.")
    endpoint = _duration_parameter(duration, "endpoint")
    if endpoint == "phase":
        return EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        )
    if endpoint == "turn":
        return EffectExpiration.end_turn(
            battle_round=use_record.battle_round,
            player_id=context.active_player_id or use_record.player_id,
        )
    if endpoint == "battle":
        return EffectExpiration.end_of_battle()
    raise GameLifecycleError("Generic persisted Stratagem effect endpoint is unsupported.")


def _duration_parameter(duration_payload: dict[str, JsonValue], key: str) -> str:
    requested_key = _validate_identifier("duration parameter", key)
    parameters = duration_payload.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic effect duration parameters must be a list.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Generic effect duration parameter must be an object.")
        if parameter.get("key") != requested_key:
            continue
        value = parameter.get("value")
        if type(value) is not str:
            raise GameLifecycleError("Generic effect duration parameter must be a string.")
        return _validate_identifier(requested_key, value)
    raise GameLifecycleError("Generic effect duration parameter is missing.")


def _runtime_effect_event_payload(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect: PersistingEffect,
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "player_id": use_record.player_id,
        "battle_round": use_record.battle_round,
        "phase": use_record.phase.value,
        "active_player_id": context.active_player_id,
        "stratagem_use": validate_json_value(use_record.to_payload()),
        "persisting_effect": validate_json_value(effect.to_payload()),
    }


def _required_rule_effect_string_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> str:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not str:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a string.")
    return _validate_identifier(key, value)


def _optional_rule_effect_string_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> str | None:
    value = _rule_effect_parameter(effect_payload, key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a string.")
    return _validate_identifier(key, value)


def _required_rule_effect_number_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> float:
    value = _rule_effect_parameter(effect_payload, key)
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be numeric.")
    return float(value)
