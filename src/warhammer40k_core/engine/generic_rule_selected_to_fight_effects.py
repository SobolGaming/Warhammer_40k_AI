from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedTimedEffect,
)
from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionResult,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
)


@dataclass(frozen=True, slots=True)
class SelectedToFightEnhancementBearer:
    army: ArmyDefinition
    assignment: EnhancementAssignment
    physical_unit: UnitInstance
    model: ModelInstance
    selected_rules_unit_instance_id: str

    def __post_init__(self) -> None:
        if type(self.army) is not ArmyDefinition:
            raise GameLifecycleError("Selected-to-fight bearer requires ArmyDefinition.")
        if type(self.assignment) is not EnhancementAssignment:
            raise GameLifecycleError("Selected-to-fight bearer requires assignment.")
        if type(self.physical_unit) is not UnitInstance:
            raise GameLifecycleError("Selected-to-fight bearer requires physical unit.")
        if type(self.model) is not ModelInstance:
            raise GameLifecycleError("Selected-to-fight bearer requires model.")
        object.__setattr__(
            self,
            "selected_rules_unit_instance_id",
            _validate_identifier(
                "selected_rules_unit_instance_id",
                self.selected_rules_unit_instance_id,
            ),
        )


def selected_to_fight_enhancement_bearer_is_alive(
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Selected-to-fight bearer lookup requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Selected-to-fight bearer lookup requires source.")
    if type(matching_effects) is not tuple:
        raise GameLifecycleError("Selected-to-fight matching effects must be a tuple.")
    return _selected_to_fight_enhancement_bearer(context=context, source=source).model.is_alive


def build_selected_to_fight_self_mortal_wounds_and_rerolls_grant(
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    *,
    ability_id: str,
    hook_id: str,
    label: str,
) -> FightUnitSelectedGrant:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Selected-to-fight grant requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Selected-to-fight grant requires source.")
    if type(matching_effects) is not tuple:
        raise GameLifecycleError("Selected-to-fight grant effects must be a tuple.")
    requested_ability = _validate_identifier("ability_id", ability_id)
    requested_hook_id = _validate_identifier("hook_id", hook_id)
    if type(label) is not str or not label.strip():
        raise GameLifecycleError("Selected-to-fight grant label must be non-empty.")
    bearer = _selected_to_fight_enhancement_bearer(context=context, source=source)
    result = execute_rule_ir(
        rule_ir=source.rule_ir,
        context=RuleExecutionContext(
            game_id=context.state.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=BattlePhase.FIGHT,
            active_player_id=context.state.active_player_id,
            source_unit_instance_id=bearer.selected_rules_unit_instance_id,
            source_model_instance_id=bearer.model.model_instance_id,
            target_unit_instance_ids=(bearer.selected_rules_unit_instance_id,),
            target_player_id=context.player_id,
            trigger_payload={
                "event": "unit_selected_to_fight",
                "phase": BattlePhase.FIGHT.value,
                "timing_window": "selected_to_fight",
                "unit_instance_id": context.unit_instance_id,
                "activation_request_id": context.request_id,
                "activation_result_id": context.result_id,
                "fight_type": context.fight_type,
                "ordering_band": context.ordering_band,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "enhancement_assignment": validate_json_value(bearer.assignment.to_payload()),
            },
            state=context.state,
            record_persisting_effects=False,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        reason = "missing_reason" if result.reason is None else result.reason
        raise GameLifecycleError(f"Selected-to-fight RuleIR failed: {reason}.")
    timed_effects, immediate_effect = _selected_to_fight_effects(
        source=source,
        result=result,
        assignment=bearer.assignment,
        ability_id=requested_ability,
    )
    return FightUnitSelectedGrant(
        hook_id=requested_hook_id,
        source_id=source.record.execution_id,
        label=label.strip(),
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_selected_to_fight_grant",
                "execution_id": source.record.execution_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "rule_ir_source_id": source.rule_ir.source_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "enhancement_assignment": bearer.assignment.to_payload(),
                "bearer_unit_instance_id": bearer.physical_unit.unit_instance_id,
                "bearer_model_instance_id": bearer.model.model_instance_id,
                "selected_rules_unit_instance_id": bearer.selected_rules_unit_instance_id,
                "rule_execution_result": result.to_payload(),
            }
        ),
        timed_effects=timed_effects,
        immediate_effect_payload=immediate_effect,
    )


def _selected_to_fight_effects(
    *,
    source: GenericRuleAbilitySource,
    result: RuleExecutionResult,
    assignment: EnhancementAssignment,
    ability_id: str,
) -> tuple[tuple[FightUnitSelectedTimedEffect, ...], JsonValue]:
    timed_effects: list[FightUnitSelectedTimedEffect] = []
    immediate_effects: list[dict[str, JsonValue]] = []
    grant_count = 0
    reroll_types: set[str] = set()
    for raw_payload in result.effect_payloads:
        payload = _enriched_effect_payload(
            raw_payload,
            source=source,
            assignment=assignment,
        )
        kind = _effect_kind(payload)
        parameters = _effect_parameters(payload)
        _require_this_model_target(payload)
        if kind is RuleEffectKind.GRANT_ABILITY:
            if parameters.get("ability") != ability_id:
                raise GameLifecycleError(
                    "Selected-to-fight RuleIR contains an unrelated ability grant."
                )
            grant_count += 1
            continue
        if kind is RuleEffectKind.INFLICT_MORTAL_WOUNDS:
            _validate_self_mortal_wound_parameters(parameters)
            immediate_effects.append(payload)
            continue
        if kind is RuleEffectKind.REROLL_PERMISSION:
            roll_type = parameters.get("roll_type")
            if roll_type not in {"hit", "wound"}:
                raise GameLifecycleError(
                    "Selected-to-fight reroll permission must be for Hit or Wound."
                )
            if "reroll_unmodified_value" in parameters:
                raise GameLifecycleError("Selected-to-fight reroll must permit the whole roll.")
            if roll_type in reroll_types:
                raise GameLifecycleError("Selected-to-fight reroll permissions are duplicated.")
            reroll_types.add(roll_type)
            _require_end_phase_duration(payload)
            timed_effects.append(
                FightUnitSelectedTimedEffect(
                    effect_payload=payload,
                    expiration="end_phase",
                )
            )
            continue
        raise GameLifecycleError("Selected-to-fight RuleIR contains an unsupported effect.")
    if grant_count != 1:
        raise GameLifecycleError("Selected-to-fight RuleIR requires one hook ability grant.")
    if len(immediate_effects) != 1:
        raise GameLifecycleError("Selected-to-fight RuleIR requires one immediate effect.")
    if reroll_types != {"hit", "wound"}:
        raise GameLifecycleError("Selected-to-fight RuleIR requires Hit and Wound rerolls.")
    return tuple(timed_effects), immediate_effects[0]


def _selected_to_fight_enhancement_bearer(
    *,
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
) -> SelectedToFightEnhancementBearer:
    if (
        source.record.coverage_kind
        is not faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
    ):
        raise GameLifecycleError("Selected-to-fight generic source must be an Enhancement.")
    enhancement_id = source.record.rule_id
    if enhancement_id is None:
        raise GameLifecycleError("Selected-to-fight Enhancement source requires rule_id.")
    army = context.state.army_definition_for_player(context.player_id)
    if army is None:
        raise GameLifecycleError("Selected-to-fight Enhancement requires player army.")
    assignments = tuple(
        assignment
        for assignment in army.enhancement_assignments
        if assignment.enhancement_id == enhancement_id
    )
    if len(assignments) != 1:
        raise GameLifecycleError(
            "Selected-to-fight Enhancement requires exactly one bearer assignment."
        )
    assignment = assignments[0]
    bearer_unit_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
    bearer_units = tuple(unit for unit in army.units if unit.unit_instance_id == bearer_unit_id)
    if len(bearer_units) != 1:
        raise GameLifecycleError("Selected-to-fight Enhancement bearer unit is missing.")
    bearer_unit = bearer_units[0]
    if len(bearer_unit.own_models) != 1:
        raise GameLifecycleError(
            "Selected-to-fight Enhancement requires a single-model bearer unit."
        )
    selected_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
    )
    if bearer_unit_id not in selected_rules_unit.component_unit_instance_ids:
        raise GameLifecycleError(
            "Selected-to-fight Enhancement bearer is not in the selected rules unit."
        )
    return SelectedToFightEnhancementBearer(
        army=army,
        assignment=assignment,
        physical_unit=bearer_unit,
        model=bearer_unit.own_models[0],
        selected_rules_unit_instance_id=selected_rules_unit.unit_instance_id,
    )


def _enriched_effect_payload(
    value: dict[str, JsonValue],
    *,
    source: GenericRuleAbilitySource,
    assignment: EnhancementAssignment,
) -> dict[str, JsonValue]:
    return _json_object(
        validate_json_value(
            {
                **value,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "enhancement_assignment": assignment.to_payload(),
            }
        )
    )


def _effect_kind(payload: dict[str, JsonValue]) -> RuleEffectKind:
    effect = _json_object(payload.get("effect"))
    value = effect.get("kind")
    if type(value) is not str:
        raise GameLifecycleError("Selected-to-fight effect kind must be a string.")
    try:
        return RuleEffectKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Selected-to-fight effect kind is unsupported.") from exc


def _effect_parameters(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    effect = _json_object(payload.get("effect"))
    raw_parameters = effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Selected-to-fight effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        parameter = _json_object(raw_parameter)
        key = parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Selected-to-fight effect parameter requires key.")
        identifier = _validate_identifier("parameter key", key)
        if identifier in parameters:
            raise GameLifecycleError("Selected-to-fight effect parameters are duplicated.")
        parameters[identifier] = validate_json_value(parameter.get("value"))
    return parameters


def _require_this_model_target(payload: dict[str, JsonValue]) -> None:
    target = _json_object(payload.get("target"))
    if target.get("kind") != RuleTargetKind.THIS_MODEL.value:
        raise GameLifecycleError("Selected-to-fight effects must target this model.")


def _validate_self_mortal_wound_parameters(parameters: dict[str, JsonValue]) -> None:
    if parameters.get("mortal_wounds_dice_quantity") != 1:
        raise GameLifecycleError("Selected-to-fight mortal wounds require one die.")
    if parameters.get("mortal_wounds_dice_sides") != 3:
        raise GameLifecycleError("Selected-to-fight mortal wounds require a D3.")
    if parameters.get("mortal_wounds_modifier") != 1:
        raise GameLifecycleError("Selected-to-fight mortal wounds require a +1 modifier.")


def _require_end_phase_duration(payload: dict[str, JsonValue]) -> None:
    duration = _json_object(payload.get("duration"))
    if duration.get("kind") != "until_timing_endpoint":
        raise GameLifecycleError("Selected-to-fight reroll duration is unsupported.")
    raw_parameters = duration.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Selected-to-fight duration parameters must be a list.")
    parameters = {
        _validate_identifier("duration parameter key", _json_object(item).get("key")): (
            _json_object(item).get("value")
        )
        for item in raw_parameters
    }
    if parameters != {"endpoint": "phase"}:
        raise GameLifecycleError("Selected-to-fight rerolls must expire at phase end.")


def _json_object(value: object) -> dict[str, JsonValue]:
    validated = validate_json_value(value)
    if not isinstance(validated, dict):
        raise GameLifecycleError("Selected-to-fight payload must be an object.")
    return validated


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "SelectedToFightEnhancementBearer",
    "build_selected_to_fight_self_mortal_wounds_and_rerolls_grant",
    "selected_to_fight_enhancement_bearer_is_alive",
)
