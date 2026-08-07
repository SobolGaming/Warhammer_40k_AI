from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectBinding,
    EnhancementEffectContext,
    EnhancementEffectHandler,
    EnhancementPersistingEffectGrant,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import (
    RuntimeContentActivation,
    RuntimeEnhancementAssignment,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_weapon_ability_granted_profile,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
    WeaponProfileModifierHandler,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_rule_ir_promotion_2026_07,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord
_RULE_IR_AURA_TEMPLATE_ID = "phase17c:aura"

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class _GenericEnhancementBindingSource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR
    assignments_by_id: Mapping[str, RuntimeEnhancementAssignment]

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic enhancement binding requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic enhancement binding requires RuleIR.")
        if self.record.rule_id is None:
            raise GameLifecycleError("Generic enhancement execution record requires rule_id.")
        object.__setattr__(
            self,
            "assignments_by_id",
            _validate_assignment_mapping(self.assignments_by_id),
        )


@dataclass(frozen=True, slots=True)
class _GenericAuraWeaponBindingSource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR
    assignment: RuntimeEnhancementAssignment

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic aura weapon binding requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic aura weapon binding requires RuleIR.")
        if type(self.assignment) is not RuntimeEnhancementAssignment:
            raise GameLifecycleError("Generic aura weapon binding requires assignment.")


def generic_enhancement_effect_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
    rule_ir_resolver: Callable[[str], RuleIR] = (
        faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id
    ),
) -> tuple[EnhancementEffectBinding, ...]:
    bindings: list[EnhancementEffectBinding] = []
    for source in _generic_enhancement_binding_sources(
        activation=activation,
        execution_records=execution_records,
        rule_ir_resolver=rule_ir_resolver,
    ):
        if _rule_ir_has_specialized_runtime_hook_family(source.rule_ir):
            continue
        _validate_enhancement_rule_ir(source.rule_ir)
        bindings.append(
            EnhancementEffectBinding(
                effect_id=source.record.execution_id,
                source_id=source.rule_ir.source_id,
                enhancement_id=_record_enhancement_id(source.record),
                handler=_handler_for_source(source),
            )
        )
    return tuple(sorted(bindings, key=lambda binding: binding.effect_id))


def generic_enhancement_aura_weapon_profile_modifier_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
    rule_ir_resolver: Callable[[str], RuleIR] = (
        faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id
    ),
) -> tuple[WeaponProfileModifierBinding, ...]:
    bindings: list[WeaponProfileModifierBinding] = []
    for source in _generic_enhancement_binding_sources(
        activation=activation,
        execution_records=execution_records,
        rule_ir_resolver=rule_ir_resolver,
    ):
        if not rule_ir_has_dynamic_aura_weapon_grant(source.rule_ir):
            continue
        _validate_dynamic_aura_weapon_grant_rule_ir(source.rule_ir)
        for assignment in source.assignments_by_id.values():
            aura_source = _GenericAuraWeaponBindingSource(
                record=source.record,
                rule_ir=source.rule_ir,
                assignment=assignment,
            )
            bindings.append(
                WeaponProfileModifierBinding(
                    modifier_id=_aura_weapon_modifier_id(aura_source),
                    source_id=source.rule_ir.source_id,
                    handler=_aura_weapon_handler_for_source(aura_source),
                )
            )
    return tuple(sorted(bindings, key=lambda binding: binding.modifier_id))


def rule_ir_has_dynamic_aura_weapon_grant(rule_ir: RuleIR) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic aura weapon lookup requires RuleIR.")
    return any(
        clause.template_id == _RULE_IR_AURA_TEMPLATE_ID
        and any(effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY for effect in clause.effects)
        for clause in rule_ir.clauses
    )


def _generic_enhancement_binding_sources(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
    rule_ir_resolver: Callable[[str], RuleIR],
) -> tuple[_GenericEnhancementBindingSource, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic enhancement bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic enhancement bindings require execution records.")
    if not callable(rule_ir_resolver):
        raise GameLifecycleError("Generic enhancement RuleIR resolver must be callable.")
    assignments_by_enhancement_id = _assignments_by_enhancement_id(activation)
    if not assignments_by_enhancement_id:
        return ()
    sources: list[_GenericEnhancementBindingSource] = []
    for record in execution_records:
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic enhancement bindings require execution records.")
        if not _record_is_generic_enhancement(record):
            continue
        assignments = assignments_by_enhancement_id.get(_record_enhancement_id(record))
        if assignments is None:
            continue
        rule_ir = rule_ir_resolver(record.coverage_descriptor_id)
        if type(rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic enhancement RuleIR resolver returned invalid value.")
        if rule_ir.ir_hash() != record.rule_ir_hash:
            raise GameLifecycleError("Generic enhancement execution record has stale rule_ir_hash.")
        sources.append(
            _GenericEnhancementBindingSource(
                record=record,
                rule_ir=rule_ir,
                assignments_by_id=assignments,
            )
        )
    return tuple(sorted(sources, key=lambda source: source.record.execution_id))


def _aura_weapon_handler_for_source(
    binding_source: _GenericAuraWeaponBindingSource,
) -> WeaponProfileModifierHandler:
    def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
        return _aura_weapon_profile(context=context, binding_source=binding_source)

    return handler


def _aura_weapon_profile(
    *,
    context: WeaponProfileModifierContext,
    binding_source: _GenericAuraWeaponBindingSource,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Generic aura weapon modifier requires context.")
    bearer = _bearer_unit_for_assignment(
        state=context.state,
        assignment=binding_source.assignment,
    )
    source_model_instance_id = _source_model_instance_id(bearer)
    if not _source_model_is_active(
        state=context.state,
        bearer=bearer,
        source_model_instance_id=source_model_instance_id,
    ):
        return context.weapon_profile
    result = execute_rule_ir(
        rule_ir=binding_source.rule_ir,
        context=RuleExecutionContext(
            game_id=context.state.game_id,
            player_id=binding_source.assignment.player_id,
            battle_round=max(1, context.state.battle_round),
            phase=context.source_phase,
            active_player_id=context.state.active_player_id,
            source_unit_instance_id=binding_source.assignment.bearer_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            target_player_id=binding_source.assignment.player_id,
            trigger_payload={
                "event": "weapon_profile_modifier_query",
                "enhancement_assignment": _assignment_payload_json(binding_source.assignment),
            },
            state=context.state,
            record_persisting_effects=False,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        raise GameLifecycleError("Generic aura weapon RuleIR did not apply.")
    attacking_rules_unit_id = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    ).unit_instance_id
    profile = context.weapon_profile
    for effect_payload in result.effect_payloads:
        effect = _effect_spec_for_payload(
            rule_ir=binding_source.rule_ir,
            effect_payload=effect_payload,
        )
        if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
            raise GameLifecycleError("Generic aura weapon RuleIR returned an unexpected effect.")
        if attacking_rules_unit_id not in _target_unit_ids_from_rule_payload(effect_payload):
            continue
        profile = rule_ir_weapon_ability_granted_profile(
            parameters=parameter_payload(effect.parameters),
            profile=profile,
            source_id=_aura_weapon_effect_source_id(
                rule_ir=binding_source.rule_ir,
                effect_payload=effect_payload,
            ),
        )
    return profile


def _handler_for_source(
    binding_source: _GenericEnhancementBindingSource,
) -> EnhancementEffectHandler:
    def handler(context: EnhancementEffectContext) -> tuple[object, ...]:
        return _generic_enhancement_effects(
            context=context,
            binding_source=binding_source,
        )

    return handler


def _generic_enhancement_effects(
    *,
    context: EnhancementEffectContext,
    binding_source: _GenericEnhancementBindingSource,
) -> tuple[EnhancementPersistingEffectGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Generic enhancement effects require context.")
    if type(binding_source) is not _GenericEnhancementBindingSource:
        raise GameLifecycleError("Generic enhancement effects require binding source.")
    assignment = _selected_assignment_for_context(
        context=context,
        binding_source=binding_source,
    )
    rule_context = _rule_execution_context(context=context, assignment=assignment)
    result = execute_rule_ir(rule_ir=binding_source.rule_ir, context=rule_context)
    if result.status is not RuleExecutionStatus.APPLIED:
        raise GameLifecycleError("Generic enhancement RuleIR did not apply.")
    grants: list[EnhancementPersistingEffectGrant] = []
    for effect_payload in result.effect_payloads:
        payload = _enhancement_effect_payload(
            effect_payload=effect_payload,
            assignment=assignment,
            record=binding_source.record,
        )
        target_unit_instance_ids = _target_unit_instance_ids_from_payload(
            payload=payload,
            expected_bearer_unit_instance_id=context.target_unit.unit_instance_id,
        )
        persisting_effect = generic_rule_persisting_effect(
            effect_id=_persisting_effect_id(
                record=binding_source.record,
                assignment=assignment,
                effect_payload=payload,
            ),
            source_rule_id=binding_source.rule_ir.source_id,
            owner_player_id=context.army.player_id,
            target_unit_instance_ids=target_unit_instance_ids,
            started_battle_round=_started_battle_round(context),
            started_phase=context.state.current_battle_phase,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload=payload,
        )
        replay_payload: dict[str, JsonValue] = {
            "execution_id": binding_source.record.execution_id,
            "coverage_descriptor_id": binding_source.record.coverage_descriptor_id,
            "enhancement_assignment": _assignment_payload_json(assignment),
            "rule_execution_result": _json_object(validate_json_value(result.to_payload())),
        }
        grants.append(
            EnhancementPersistingEffectGrant(
                effect_id=binding_source.record.execution_id,
                source_id=binding_source.rule_ir.source_id,
                enhancement_id=_record_enhancement_id(binding_source.record),
                target_unit_instance_id=context.target_unit.unit_instance_id,
                persisting_effect=persisting_effect,
                replay_payload=replay_payload,
            )
        )
    return tuple(grants)


def _assignments_by_enhancement_id(
    activation: RuntimeContentActivation,
) -> Mapping[str, Mapping[str, RuntimeEnhancementAssignment]]:
    assignments_by_enhancement_id: dict[str, dict[str, RuntimeEnhancementAssignment]] = {}
    for assignment in activation.selected_enhancement_assignments:
        assignments_by_enhancement_id.setdefault(assignment.enhancement_id, {})[
            assignment.assignment_id
        ] = assignment
    return MappingProxyType(
        {
            enhancement_id: MappingProxyType(assignments)
            for enhancement_id, assignments in assignments_by_enhancement_id.items()
        }
    )


def _record_is_generic_enhancement(record: _Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _record_enhancement_id(record: _Phase17FExecutionRecord) -> str:
    if record.rule_id is None:
        raise GameLifecycleError("Generic enhancement execution record requires rule_id.")
    return _validate_identifier("enhancement_id", record.rule_id)


def _validate_enhancement_rule_ir(rule_ir: RuleIR) -> None:
    for clause in rule_ir.clauses:
        if clause.effects and clause.duration is not None:
            raise GameLifecycleError(
                "Generic enhancement assignment owns effect duration semantics."
            )


def _validate_dynamic_aura_weapon_grant_rule_ir(rule_ir: RuleIR) -> None:
    if not rule_ir.is_supported:
        raise GameLifecycleError("Generic aura weapon RuleIR must be supported.")
    grant_count = 0
    for clause in rule_ir.clauses:
        if clause.unsupported_reason is not None or clause.diagnostics:
            raise GameLifecycleError("Generic aura weapon RuleIR contains diagnostics.")
        if not clause.effects:
            continue
        if clause.template_id != _RULE_IR_AURA_TEMPLATE_ID:
            raise GameLifecycleError("Generic aura weapon effects require the aura template.")
        if clause.target is None or clause.target.kind is not RuleTargetKind.AURA_UNITS:
            raise GameLifecycleError("Generic aura weapon effects require aura-unit targets.")
        if clause.trigger is not None or clause.duration is not None:
            raise GameLifecycleError("Generic aura weapon effects must be continuously evaluated.")
        condition_kinds = {condition.kind for condition in clause.conditions}
        if not {
            RuleConditionKind.AURA,
            RuleConditionKind.DISTANCE_PREDICATE,
        }.issubset(condition_kinds):
            raise GameLifecycleError(
                "Generic aura weapon effects require aura and distance conditions."
            )
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
                raise GameLifecycleError("Generic aura weapon RuleIR contains another effect kind.")
            parameters = parameter_payload(effect.parameters)
            weapon_ability = parameters.get("weapon_ability")
            if type(weapon_ability) is not str or not weapon_ability.strip():
                raise GameLifecycleError("Generic aura weapon effect requires weapon_ability.")
            weapon_scope = parameters.get("weapon_scope")
            if weapon_scope not in {"all", "melee", "ranged"}:
                raise GameLifecycleError("Generic aura weapon effect has unsupported weapon_scope.")
            grant_count += 1
    if grant_count < 1:
        raise GameLifecycleError("Generic aura weapon RuleIR requires a weapon ability grant.")


def _rule_ir_has_specialized_runtime_hook_family(rule_ir: RuleIR) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic enhancement hook-family lookup requires RuleIR.")
    if rule_ir_has_dynamic_aura_weapon_grant(rule_ir):
        return True
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.GRANT_ABILITY:
                continue
            hook_family = parameter_payload(effect.parameters).get("hook_family")
            if hook_family is None:
                continue
            if type(hook_family) is not str:
                raise GameLifecycleError("Generic enhancement hook_family must be a string.")
            return True
    return False


def _selected_assignment_for_context(
    *,
    context: EnhancementEffectContext,
    binding_source: _GenericEnhancementBindingSource,
) -> RuntimeEnhancementAssignment:
    assignment_id = _assignment_id(
        army_id=context.army.army_id,
        enhancement_id=context.assignment.enhancement_id,
        target_unit_selection_id=context.assignment.target_unit_selection_id,
    )
    selected_assignment = binding_source.assignments_by_id.get(assignment_id)
    if selected_assignment is None:
        raise GameLifecycleError("Generic enhancement assignment is not activation-selected.")
    if selected_assignment.player_id != context.army.player_id:
        raise GameLifecycleError("Generic enhancement assignment player drift.")
    if selected_assignment.source_id != context.assignment.source_id:
        raise GameLifecycleError("Generic enhancement assignment source drift.")
    if selected_assignment.bearer_unit_instance_id != context.target_unit.unit_instance_id:
        raise GameLifecycleError("Generic enhancement assignment bearer drift.")
    return selected_assignment


def _rule_execution_context(
    *,
    context: EnhancementEffectContext,
    assignment: RuntimeEnhancementAssignment,
) -> RuleExecutionContext:
    trigger_payload: dict[str, JsonValue] = {
        "event": "enhancement_assignment",
        "enhancement_assignment": _assignment_payload_json(assignment),
    }
    return RuleExecutionContext(
        game_id=context.state.game_id,
        player_id=context.army.player_id,
        battle_round=_started_battle_round(context),
        phase=context.state.current_battle_phase,
        active_player_id=context.state.active_player_id,
        source_unit_instance_id=context.target_unit.unit_instance_id,
        source_model_instance_id=_source_model_instance_id(context.target_unit),
        target_unit_instance_ids=(context.target_unit.unit_instance_id,),
        target_player_id=context.army.player_id,
        trigger_payload=trigger_payload,
        state=context.state,
    )


def _enhancement_effect_payload(
    *,
    effect_payload: dict[str, JsonValue],
    assignment: RuntimeEnhancementAssignment,
    record: _Phase17FExecutionRecord,
) -> dict[str, JsonValue]:
    payload = {
        **effect_payload,
        "coverage_descriptor_id": record.coverage_descriptor_id,
        "execution_id": record.execution_id,
        "enhancement_assignment": _assignment_payload_json(assignment),
    }
    return _json_object(validate_json_value(payload))


def _target_unit_instance_ids_from_payload(
    *,
    payload: dict[str, JsonValue],
    expected_bearer_unit_instance_id: str,
) -> tuple[str, ...]:
    expected_bearer = _validate_identifier(
        "expected_bearer_unit_instance_id",
        expected_bearer_unit_instance_id,
    )
    raw_target_ids = payload.get("target_unit_instance_ids")
    if not isinstance(raw_target_ids, list) or not raw_target_ids:
        raise GameLifecycleError("Generic enhancement effect requires target unit IDs.")
    target_ids: list[str] = []
    for raw_target_id in raw_target_ids:
        target_ids.append(_validate_identifier("target_unit_instance_id", raw_target_id))
    if expected_bearer not in target_ids:
        raise GameLifecycleError("Generic enhancement effect target is not the bearer.")
    return tuple(sorted(target_ids))


def _persisting_effect_id(
    *,
    record: _Phase17FExecutionRecord,
    assignment: RuntimeEnhancementAssignment,
    effect_payload: dict[str, JsonValue],
) -> str:
    clause_id = effect_payload.get("clause_id")
    if type(clause_id) is not str:
        raise GameLifecycleError("Generic enhancement effect payload requires clause_id.")
    return _validate_identifier(
        "generic enhancement persisting effect_id",
        f"{record.execution_id}:{assignment.assignment_id}:{clause_id}:persisting",
    )


def _started_battle_round(context: EnhancementEffectContext) -> int:
    if context.state.battle_round < 1:
        return 1
    return context.state.battle_round


def _source_model_instance_id(unit: UnitInstance) -> str:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic enhancement source unit is invalid.")
    if not unit.own_models:
        raise GameLifecycleError("Generic enhancement source unit has no models.")
    return sorted(model.model_instance_id for model in unit.own_models)[0]


def _bearer_unit_for_assignment(
    *,
    state: GameState,
    assignment: RuntimeEnhancementAssignment,
) -> UnitInstance:
    army = state.army_definition_for_player(assignment.player_id)
    if army is None:
        raise GameLifecycleError("Generic aura weapon assignment player has no army.")
    if army.army_id != assignment.army_id:
        raise GameLifecycleError("Generic aura weapon assignment army drift.")
    matches = tuple(
        unit for unit in army.units if unit.unit_instance_id == assignment.bearer_unit_instance_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Generic aura weapon bearer unit is not unique.")
    return matches[0]


def _source_model_is_active(
    *,
    state: GameState,
    bearer: UnitInstance,
    source_model_instance_id: str,
) -> bool:
    source_model = next(
        (
            model
            for model in bearer.own_models
            if model.model_instance_id == source_model_instance_id
        ),
        None,
    )
    if source_model is None:
        raise GameLifecycleError("Generic aura weapon bearer model is missing.")
    battlefield = state.battlefield_state
    if battlefield is None or not source_model.is_alive:
        return False
    return battlefield.model_placement_or_none(source_model_instance_id) is not None


def _target_unit_ids_from_rule_payload(payload: dict[str, JsonValue]) -> tuple[str, ...]:
    raw_target_ids = payload.get("target_unit_instance_ids")
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Generic aura weapon effect requires target unit IDs.")
    target_ids = tuple(
        _validate_identifier("target_unit_instance_id", target_id) for target_id in raw_target_ids
    )
    if len(set(target_ids)) != len(target_ids) or target_ids != tuple(sorted(target_ids)):
        raise GameLifecycleError("Generic aura weapon target unit IDs must be unique and sorted.")
    return target_ids


def _effect_spec_for_payload(
    *,
    rule_ir: RuleIR,
    effect_payload: dict[str, JsonValue],
) -> RuleEffectSpec:
    clause_id = effect_payload.get("clause_id")
    effect_index = effect_payload.get("effect_index")
    if type(clause_id) is not str:
        raise GameLifecycleError("Generic aura weapon effect payload requires clause_id.")
    if type(effect_index) is not int:
        raise GameLifecycleError("Generic aura weapon effect payload requires effect_index.")
    clause = next(
        (candidate for candidate in rule_ir.clauses if candidate.clause_id == clause_id), None
    )
    if clause is None or not 0 <= effect_index < len(clause.effects):
        raise GameLifecycleError("Generic aura weapon effect payload has stale identity.")
    return clause.effects[effect_index]


def _aura_weapon_effect_source_id(
    *,
    rule_ir: RuleIR,
    effect_payload: dict[str, JsonValue],
) -> str:
    clause_id = effect_payload.get("clause_id")
    if type(clause_id) is not str:
        raise GameLifecycleError("Generic aura weapon effect payload requires clause_id.")
    return _validate_identifier(
        "generic aura weapon source_id",
        f"{rule_ir.source_id}:{clause_id}:{RuleEffectKind.GRANT_WEAPON_ABILITY.value}",
    )


def _aura_weapon_modifier_id(source: _GenericAuraWeaponBindingSource) -> str:
    return _validate_identifier(
        "generic aura weapon modifier_id",
        f"{source.record.execution_id}:{source.assignment.assignment_id}:aura-weapon-profile",
    )


def _assignment_id(
    *,
    army_id: str,
    enhancement_id: str,
    target_unit_selection_id: str,
) -> str:
    return _validate_identifier(
        "assignment_id",
        f"{army_id}:{enhancement_id}:{target_unit_selection_id}",
    )


def _validate_assignment_mapping(
    value: object,
) -> Mapping[str, RuntimeEnhancementAssignment]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Generic enhancement assignments must be a mapping.")
    validated: dict[str, RuntimeEnhancementAssignment] = {}
    for assignment_id, assignment in cast(Mapping[object, object], value).items():
        if type(assignment_id) is not str:
            raise GameLifecycleError("Generic enhancement assignment key must be a string.")
        resolved_assignment_id = _validate_identifier("assignment_id", assignment_id)
        if type(assignment) is not RuntimeEnhancementAssignment:
            raise GameLifecycleError(
                "Generic enhancement assignments must contain runtime assignments."
            )
        if assignment.assignment_id != resolved_assignment_id:
            raise GameLifecycleError("Generic enhancement assignment key drift.")
        validated[resolved_assignment_id] = assignment
    return MappingProxyType(dict(sorted(validated.items())))


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Generic enhancement effect payload must be a JSON object.")
    return value


def _assignment_payload_json(
    assignment: RuntimeEnhancementAssignment,
) -> dict[str, JsonValue]:
    return _json_object(validate_json_value(assignment.to_payload()))


_validate_identifier = IdentifierValidator(GameLifecycleError)
