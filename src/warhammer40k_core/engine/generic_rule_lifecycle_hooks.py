from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import (
    RuntimeContentActivation,
    RuntimeEnhancementAssignment,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHandler,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
    FightActivationAbilityContext,
    FightActivationAbilityHandler,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.fight_order import CHARGE_FIGHTS_FIRST_EFFECT_KIND
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR, parameter_payload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord

_FALL_BACK_SHOOT_ABILITY = "can_fall_back_and_shoot"
_FALL_BACK_CHARGE_ABILITY = "can_fall_back_and_charge"
_FIGHT_ACTIVATION_TARGETING_ABILITY = "fight_activation_melee_targeting_distance"


@dataclass(frozen=True, slots=True)
class _GenericFallBackEligibilitySource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic Fall Back source requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic Fall Back source requires RuleIR.")
        _validate_record_rule_ir_hash(record=self.record, rule_ir=self.rule_ir)


@dataclass(frozen=True, slots=True)
class _GenericFightActivationAbilitySource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR
    assignments_by_bearer_unit_id: Mapping[str, RuntimeEnhancementAssignment]

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic fight activation source requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic fight activation source requires RuleIR.")
        if self.record.rule_id is None:
            raise GameLifecycleError("Generic fight activation source requires rule_id.")
        _validate_record_rule_ir_hash(record=self.record, rule_ir=self.rule_ir)
        object.__setattr__(
            self,
            "assignments_by_bearer_unit_id",
            _validate_assignment_mapping(self.assignments_by_bearer_unit_id),
        )


def fall_back_eligibility_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[FallBackEligibilityHookBinding, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic Fall Back bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic Fall Back bindings require execution records.")
    selected_detachment_ids = set(activation.selected_detachment_ids)
    bindings: list[FallBackEligibilityHookBinding] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic Fall Back bindings require execution records.")
        if not _record_is_generic_detachment_rule(record):
            continue
        if record.detachment_id not in selected_detachment_ids:
            continue
        rule_ir = _rule_ir_for_record(record)
        if not _rule_ir_grants_any_ability(
            rule_ir,
            abilities=(_FALL_BACK_SHOOT_ABILITY, _FALL_BACK_CHARGE_ABILITY),
        ):
            continue
        source = _GenericFallBackEligibilitySource(record=record, rule_ir=rule_ir)
        bindings.append(
            FallBackEligibilityHookBinding(
                hook_id=_fall_back_hook_id(record),
                source_id=rule_ir.source_id,
                handler=_fall_back_handler_for_source(source),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def fight_activation_ability_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
) -> tuple[FightActivationAbilityHookBinding, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic fight activation bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic fight activation bindings require execution records.")
    assignments_by_enhancement_id = _assignments_by_enhancement_id(activation)
    bindings: list[FightActivationAbilityHookBinding] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic fight activation bindings require execution records.")
        if not _record_is_generic_enhancement(record):
            continue
        enhancement_id = _record_rule_id(record)
        assignments = assignments_by_enhancement_id.get(enhancement_id)
        if assignments is None:
            continue
        rule_ir = _rule_ir_for_record(record)
        if not _rule_ir_grants_any_ability(
            rule_ir,
            abilities=(_FIGHT_ACTIVATION_TARGETING_ABILITY,),
        ):
            continue
        source = _GenericFightActivationAbilitySource(
            record=record,
            rule_ir=rule_ir,
            assignments_by_bearer_unit_id=assignments,
        )
        bindings.append(
            FightActivationAbilityHookBinding(
                hook_id=_fight_activation_hook_id(record),
                source_id=rule_ir.source_id,
                handler=_fight_activation_handler_for_source(source),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _fall_back_handler_for_source(
    source: _GenericFallBackEligibilitySource,
) -> FallBackEligibilityHandler:
    def handler(context: FallBackEligibilityContext) -> FallBackEligibilityGrant | None:
        return _fall_back_grant_for_context(context=context, source=source)

    return handler


def _fall_back_grant_for_context(
    *,
    context: FallBackEligibilityContext,
    source: _GenericFallBackEligibilitySource,
) -> FallBackEligibilityGrant | None:
    if type(context) is not FallBackEligibilityContext:
        raise GameLifecycleError("Generic Fall Back grant requires context.")
    if type(source) is not _GenericFallBackEligibilitySource:
        raise GameLifecycleError("Generic Fall Back grant requires source.")
    army = _army_for_player(state=context.state, player_id=context.player_id)
    if not _army_uses_detachment_record(army=army, record=source.record):
        return None
    unit = _unit_in_army(army=army, unit_instance_id=context.unit_instance_id)
    result = execute_rule_ir(
        rule_ir=source.rule_ir,
        context=RuleExecutionContext(
            game_id=context.state.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.state.current_battle_phase,
            active_player_id=context.state.active_player_id,
            source_unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            target_player_id=context.player_id,
            trigger_payload={
                "event": "fall_back_eligibility",
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
            },
            state=context.state,
            record_persisting_effects=False,
        ),
    )
    if (
        result.status is RuleExecutionStatus.INVALID
        and result.reason == "unit_missing_required_keyword"
    ):
        return None
    if result.status is not RuleExecutionStatus.APPLIED:
        if result.reason is None:
            raise GameLifecycleError("Generic Fall Back RuleIR failed without reason.")
        raise GameLifecycleError(f"Generic Fall Back RuleIR failed: {result.reason}.")
    can_shoot = _effect_payloads_grant_ability(
        result.effect_payloads,
        ability=_FALL_BACK_SHOOT_ABILITY,
    )
    can_declare_charge = _effect_payloads_grant_ability(
        result.effect_payloads,
        ability=_FALL_BACK_CHARGE_ABILITY,
    )
    if not can_shoot and not can_declare_charge:
        return None
    return FallBackEligibilityGrant(
        hook_id=_fall_back_hook_id(source.record),
        source_id=source.rule_ir.source_id,
        can_shoot=can_shoot,
        can_declare_charge=can_declare_charge,
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_fall_back_eligibility",
                "execution_id": source.record.execution_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "unit_instance_id": unit.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
                "rule_execution_result": result.to_payload(),
            }
        ),
    )


def _fight_activation_handler_for_source(
    source: _GenericFightActivationAbilitySource,
) -> FightActivationAbilityHandler:
    def handler(context: FightActivationAbilityContext) -> FightActivationAbilityOption | None:
        return _fight_activation_option_for_context(context=context, source=source)

    return handler


def _fight_activation_option_for_context(
    *,
    context: FightActivationAbilityContext,
    source: _GenericFightActivationAbilitySource,
) -> FightActivationAbilityOption | None:
    if type(context) is not FightActivationAbilityContext:
        raise GameLifecycleError("Generic fight activation option requires context.")
    if type(source) is not _GenericFightActivationAbilitySource:
        raise GameLifecycleError("Generic fight activation option requires source.")
    assignment = source.assignments_by_bearer_unit_id.get(context.unit_instance_id)
    if assignment is None:
        return None
    if assignment.player_id != context.player_id:
        raise GameLifecycleError("Generic fight activation assignment player drift.")
    if not context.target_unit_instance_ids:
        return None
    result = execute_rule_ir(
        rule_ir=source.rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.state.current_battle_phase,
            active_player_id=context.active_player_id,
            source_unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=(context.unit_instance_id,),
            target_player_id=context.player_id,
            trigger_payload={
                "event": "fight_activation_ability",
                "activation": validate_json_value(context.activation.to_payload()),
                "target_unit_instance_ids": list(context.target_unit_instance_ids),
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "enhancement_assignment": validate_json_value(assignment.to_payload()),
            },
            state=context.state,
            record_persisting_effects=False,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        if result.reason is None:
            raise GameLifecycleError("Generic fight activation RuleIR failed without reason.")
        raise GameLifecycleError(f"Generic fight activation RuleIR failed: {result.reason}.")
    effect_payload = _single_grant_ability_payload(
        result.effect_payloads,
        ability=_FIGHT_ACTIVATION_TARGETING_ABILITY,
    )
    parameters = _effect_parameters(effect_payload)
    if _optional_bool_parameter(parameters, "requires_charge_move") and not _unit_made_charge_move(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return FightActivationAbilityOption(
        hook_id=_fight_activation_hook_id(source.record),
        source_id=source.rule_ir.source_id,
        ability_id=_record_rule_id(source.record),
        enhancement_id=_record_rule_id(source.record),
        effect_kind=FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
        model_proximity_inches=_positive_float_parameter(parameters, "model_proximity_inches"),
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_fight_activation_ability",
                "execution_id": source.record.execution_id,
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "enhancement_assignment": assignment.to_payload(),
                "target_unit_instance_ids": list(context.target_unit_instance_ids),
                "rule_execution_result": result.to_payload(),
            }
        ),
    )


def _record_is_generic_detachment_rule(record: _Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_RULE
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _record_is_generic_enhancement(record: _Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _record_rule_id(record: _Phase17FExecutionRecord) -> str:
    if record.rule_id is None:
        raise GameLifecycleError("Generic lifecycle execution record requires rule_id.")
    return record.rule_id


def _rule_ir_for_record(record: _Phase17FExecutionRecord) -> RuleIR:
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    _validate_record_rule_ir_hash(record=record, rule_ir=rule_ir)
    return rule_ir


def _validate_record_rule_ir_hash(*, record: _Phase17FExecutionRecord, rule_ir: RuleIR) -> None:
    if record.rule_ir_hash is None:
        raise GameLifecycleError("Generic lifecycle execution record requires rule_ir_hash.")
    if rule_ir.ir_hash() != record.rule_ir_hash:
        raise GameLifecycleError("Generic lifecycle execution record has stale RuleIR hash.")


def _rule_ir_grants_any_ability(rule_ir: RuleIR, *, abilities: tuple[str, ...]) -> bool:
    expected = set(_validate_identifier_tuple("generic ability", abilities))
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.GRANT_ABILITY:
                continue
            ability = parameter_payload(effect.parameters).get("ability")
            if type(ability) is str and ability in expected:
                return True
    return False


def _effect_payloads_grant_ability(
    effect_payloads: tuple[dict[str, JsonValue], ...],
    *,
    ability: str,
) -> bool:
    requested_ability = _validate_identifier("ability", ability)
    return any(
        generic_rule_effect_payload_grants_ability(payload, ability=requested_ability)
        for payload in effect_payloads
    )


def _single_grant_ability_payload(
    effect_payloads: tuple[dict[str, JsonValue], ...],
    *,
    ability: str,
) -> dict[str, JsonValue]:
    matching = tuple(
        payload
        for payload in effect_payloads
        if generic_rule_effect_payload_grants_ability(payload, ability=ability)
    )
    if len(matching) != 1:
        raise GameLifecycleError("Generic fight activation RuleIR must grant exactly one ability.")
    return matching[0]


def _effect_parameters(effect_payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    raw_effect = effect_payload.get("effect")
    if not isinstance(raw_effect, dict):
        raise GameLifecycleError("Generic lifecycle effect payload requires effect object.")
    raw_parameters = raw_effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic lifecycle effect payload requires parameters.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic lifecycle effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic lifecycle effect parameter requires key.")
        if key in parameters:
            raise GameLifecycleError("Generic lifecycle effect parameters must be unique.")
        parameters[key] = validate_json_value(raw_parameter.get("value"))
    return parameters


def _optional_bool_parameter(parameters: Mapping[str, JsonValue], key: str) -> bool:
    value = parameters.get(key)
    if value is None:
        return False
    if type(value) is not bool:
        raise GameLifecycleError(f"Generic lifecycle parameter {key} must be a bool.")
    return value


def _positive_float_parameter(parameters: Mapping[str, JsonValue], key: str) -> float:
    value = parameters.get(key)
    if type(value) is int:
        converted = float(value)
    elif type(value) is float:
        converted = value
    else:
        raise GameLifecycleError(f"Generic lifecycle parameter {key} must be numeric.")
    if converted <= 0.0:
        raise GameLifecycleError(f"Generic lifecycle parameter {key} must be positive.")
    return converted


def _unit_made_charge_move(*, state: GameState, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") == CHARGE_FIGHTS_FIRST_EFFECT_KIND:
            return True
    return False


def _army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Generic lifecycle player army is unknown.")


def _army_uses_detachment_record(
    *,
    army: ArmyDefinition,
    record: _Phase17FExecutionRecord,
) -> bool:
    if record.detachment_id is None:
        raise GameLifecycleError("Generic lifecycle detachment record requires detachment_id.")
    return (
        army.detachment_selection.faction_id == record.faction_id
        and record.detachment_id in army.detachment_selection.detachment_ids
    )


def _unit_in_army(*, army: ArmyDefinition, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Generic lifecycle target unit is not in the selected player army.")


def _assignments_by_enhancement_id(
    activation: RuntimeContentActivation,
) -> Mapping[str, Mapping[str, RuntimeEnhancementAssignment]]:
    assignments_by_enhancement_id: dict[str, dict[str, RuntimeEnhancementAssignment]] = {}
    for assignment in activation.selected_enhancement_assignments:
        assignments_by_bearer = assignments_by_enhancement_id.setdefault(
            assignment.enhancement_id,
            {},
        )
        existing = assignments_by_bearer.get(assignment.bearer_unit_instance_id)
        if existing is not None:
            raise GameLifecycleError("Generic lifecycle enhancement assignment is duplicated.")
        assignments_by_bearer[assignment.bearer_unit_instance_id] = assignment
    return MappingProxyType(
        {
            enhancement_id: MappingProxyType(assignments)
            for enhancement_id, assignments in assignments_by_enhancement_id.items()
        }
    )


def _validate_assignment_mapping(
    value: object,
) -> Mapping[str, RuntimeEnhancementAssignment]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Generic lifecycle assignments must be a mapping.")
    validated: dict[str, RuntimeEnhancementAssignment] = {}
    for unit_id, assignment in cast(Mapping[object, object], value).items():
        resolved_unit_id = _validate_identifier("bearer_unit_instance_id", unit_id)
        if type(assignment) is not RuntimeEnhancementAssignment:
            raise GameLifecycleError(
                "Generic lifecycle assignment mapping requires runtime assignments."
            )
        if assignment.bearer_unit_instance_id != resolved_unit_id:
            raise GameLifecycleError("Generic lifecycle assignment bearer drift.")
        validated[resolved_unit_id] = assignment
    return MappingProxyType(dict(sorted(validated.items())))


def _fall_back_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic fall back hook_id",
        f"{record.execution_id}:fall-back-eligibility",
    )


def _fight_activation_hook_id(record: _Phase17FExecutionRecord) -> str:
    return _validate_identifier(
        "generic fight activation hook_id",
        f"{record.execution_id}:fight-activation-ability",
    )


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    return tuple(_validate_identifier(f"{field_name} value", value) for value in raw_values)


_validate_identifier = IdentifierValidator(GameLifecycleError)
