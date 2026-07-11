from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityContext
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedContext
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.shooting_unit_selected_hooks import ShootingUnitSelectedContext
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    parameter_payload,
)


def rule_ir_grants_any_ability(rule_ir: RuleIR, *, abilities: tuple[str, ...]) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic RuleIR ability lookup requires RuleIR.")
    expected = set(_validate_ability_ids("generic ability", abilities))
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.GRANT_ABILITY:
                continue
            ability = parameter_payload(effect.parameters).get("ability")
            if type(ability) is str and ability in expected:
                return True
    return False


def generic_rule_ability_effects_for_unit(
    *,
    state: GameState,
    source: GenericRuleAbilitySource,
    unit_instance_id: str,
    ability: str,
) -> tuple[PersistingEffect, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR ability effects require GameState.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Generic RuleIR ability effects require source.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_ability = _validate_identifier("ability", ability)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    matches: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(rules_unit.unit_instance_id):
        if not _generic_rule_effect_grants_ability(
            effect=effect,
            source=source,
            rules_unit=rules_unit,
            ability=requested_ability,
        ):
            continue
        matches.append(effect)
    return tuple(sorted(matches, key=lambda effect: effect.effect_id))


def generic_rule_ability_source_context_payload(
    *,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    source_rule_id: str,
    extra_context: Mapping[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "source_rule_id": _validate_identifier("source_rule_id", source_rule_id),
            "coverage_descriptor_id": source.record.coverage_descriptor_id,
            "execution_id": source.record.execution_id,
            "rule_ir_source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "persisting_effect_ids": generic_rule_persisting_effect_ids(matching_effects),
            **dict(extra_context),
        }
    )


def generic_rule_persisting_effect_ids(
    matching_effects: tuple[PersistingEffect, ...],
) -> list[str]:
    if type(matching_effects) is not tuple:
        raise GameLifecycleError("Generic RuleIR ability effects must be a tuple.")
    effect_ids: list[str] = []
    for effect in matching_effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Generic RuleIR ability effects require PersistingEffect.")
        effect_ids.append(effect.effect_id)
    return effect_ids


def generic_rule_ability_unit_for_player_context(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    source: GenericRuleAbilitySource,
) -> RulesUnitView | None:
    army = generic_rule_army_for_player(state=state, player_id=player_id)
    if not generic_rule_army_uses_record(army=army, source=source):
        return None
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Generic RuleIR ability unit owner drift.")
    return rules_unit


def generic_rule_army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Generic RuleIR ability player army is unknown.")


def generic_rule_army_uses_record(
    *, army: ArmyDefinition, source: GenericRuleAbilitySource
) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Generic RuleIR ability source requires ArmyDefinition.")
    if source.record.detachment_id is None:
        raise GameLifecycleError("Generic RuleIR ability detachment record requires detachment_id.")
    return (
        army.detachment_selection.faction_id == source.record.faction_id
        and source.record.detachment_id in army.detachment_selection.detachment_ids
    )


def generic_rule_advance_context_unit_id(context: AdvanceEligibilityContext) -> str:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Generic RuleIR advance ability requires context.")
    return context.unit_instance_id


def generic_rule_advance_move_context_unit_id(context: AdvanceMoveContext) -> str:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Generic RuleIR advance move ability requires context.")
    return context.unit_instance_id


def generic_rule_shooting_target_restriction_target_unit_id(
    context: ShootingTargetRestrictionContext,
) -> str:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Generic RuleIR target restriction ability requires context.")
    return context.target_unit_instance_id


def generic_rule_shooting_unit_selected_unit_id(context: ShootingUnitSelectedContext) -> str:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Generic RuleIR shooting grant ability requires context.")
    return context.unit_instance_id


def generic_rule_fight_unit_selected_unit_id(context: FightUnitSelectedContext) -> str:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Generic RuleIR fight grant ability requires context.")
    return context.unit_instance_id


def _generic_rule_effect_grants_ability(
    *,
    effect: PersistingEffect,
    source: GenericRuleAbilitySource,
    rules_unit: RulesUnitView,
    ability: str,
) -> bool:
    payload = _generic_rule_effect_payload_or_none(effect=effect, source=source)
    if payload is None:
        return False
    rule_effect = _payload_object(payload, key="effect")
    if rule_effect.get("kind") != RuleEffectKind.GRANT_ABILITY.value:
        return False
    parameters = _effect_parameters(rule_effect)
    if parameters.get("ability") != ability:
        return False
    return _required_keywords_apply(parameters=parameters, rules_unit=rules_unit)


def _generic_rule_effect_payload_or_none(
    *,
    effect: PersistingEffect,
    source: GenericRuleAbilitySource,
) -> dict[str, JsonValue] | None:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Generic RuleIR ability lookup requires PersistingEffect.")
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    if payload.get("coverage_descriptor_id") != source.record.coverage_descriptor_id:
        return None
    target_payload = payload.get("target")
    if target_payload is not None:
        if not isinstance(target_payload, dict):
            raise GameLifecycleError("Generic RuleIR ability target payload is malformed.")
        if target_payload.get("kind") != RuleTargetKind.THIS_UNIT.value:
            raise GameLifecycleError("Generic RuleIR ability effect target drift.")
    return dict(payload)


def _payload_object(payload: Mapping[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Generic RuleIR ability payload requires {key}.")
    return dict(value)


def _effect_parameters(effect_payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    raw_parameters = effect_payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic RuleIR ability effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic RuleIR ability effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic RuleIR ability effect parameter requires key.")
        resolved_key = _validate_identifier("parameter key", key)
        if resolved_key in parameters:
            raise GameLifecycleError("Generic RuleIR ability effect parameters must be unique.")
        parameters[resolved_key] = validate_json_value(raw_parameter.get("value"))
    return parameters


def _required_keywords_apply(
    *,
    parameters: Mapping[str, JsonValue],
    rules_unit: RulesUnitView,
) -> bool:
    required_keywords = _required_keyword_values(
        parameters=parameters,
        singular_key="required_keyword",
        sequence_key="required_keyword_sequence",
    )
    required_faction_keywords = _required_keyword_values(
        parameters=parameters,
        singular_key="required_faction_keyword",
        sequence_key="required_faction_keyword_sequence",
    )
    required_keyword_any = _required_keyword_any_values(parameters=parameters)
    if not required_keywords and not required_faction_keywords and required_keyword_any is None:
        return True
    if not all(_rules_unit_has_keyword(rules_unit, keyword) for keyword in required_keywords):
        return False
    if not all(
        _rules_unit_has_faction_keyword(rules_unit, keyword)
        for keyword in required_faction_keywords
    ):
        return False
    if required_keyword_any is not None:
        return any(_rules_unit_has_keyword(rules_unit, keyword) for keyword in required_keyword_any)
    return True


def _required_keyword_values(
    *,
    parameters: Mapping[str, JsonValue],
    singular_key: str,
    sequence_key: str,
) -> tuple[str, ...]:
    required_keywords: list[str] = []
    required_keyword = parameters.get(singular_key)
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError(f"Generic RuleIR ability {singular_key} must be a string.")
        required_keywords.append(required_keyword)
    required_sequence = parameters.get(sequence_key)
    if required_sequence is not None:
        if not isinstance(required_sequence, list):
            raise GameLifecycleError(f"Generic RuleIR ability {sequence_key} must be a list.")
        for item in required_sequence:
            if type(item) is not str:
                raise GameLifecycleError(
                    f"Generic RuleIR ability {sequence_key} must contain strings."
                )
            required_keywords.append(item)
    return tuple(required_keywords)


def _required_keyword_any_values(
    *,
    parameters: Mapping[str, JsonValue],
) -> tuple[str, ...] | None:
    required_keyword_any = parameters.get("required_keyword_any")
    if required_keyword_any is None:
        return None
    if not isinstance(required_keyword_any, list):
        raise GameLifecycleError("Generic RuleIR ability required_keyword_any must be a list.")
    if not required_keyword_any:
        raise GameLifecycleError("Generic RuleIR ability required_keyword_any must not be empty.")
    required_keywords: list[str] = []
    for item in required_keyword_any:
        if type(item) is not str:
            raise GameLifecycleError("Generic RuleIR ability required_keyword_any item is invalid.")
        required_keywords.append(item)
    return tuple(required_keywords)


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Generic RuleIR ability keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    return requested_keyword in {_canonical_keyword(stored) for stored in rules_unit.keywords}


def _rules_unit_has_faction_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Generic RuleIR ability keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    return requested_keyword in {
        _canonical_keyword(stored) for stored in rules_unit.faction_keywords
    }


def _validate_ability_ids(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        resolved = _validate_identifier(f"{field_name} value", value)
        if resolved in seen:
            raise GameLifecycleError(f"{field_name} values must be unique.")
        seen.add(resolved)
        validated.append(resolved)
    return tuple(validated)


def _canonical_keyword(value: str) -> str:
    return " ".join(value.upper().replace("_", " ").replace("-", " ").split())


_validate_identifier = IdentifierValidator(GameLifecycleError)
