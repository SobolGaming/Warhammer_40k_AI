from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHandler,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.generic_rule_ability_effects import (
    generic_rule_ability_effects_for_unit,
    rule_ir_grants_any_ability,
)
from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource
from warhammer40k_core.engine.generic_rule_ability_registry_defaults import (
    DEFAULT_GENERIC_RULE_ABILITY_REGISTRY,
)
from warhammer40k_core.engine.generic_rule_advance_move_abilities import (
    GenericRuleAdvanceMoveAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_rule_ir_promotion_2026_07,
)

Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord
_validate_identifier = IdentifierValidator(GameLifecycleError)


def advance_move_hook_bindings(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[Phase17FExecutionRecord, ...],
) -> tuple[AdvanceMoveHookBinding, ...]:
    bindings: list[AdvanceMoveHookBinding] = []
    for descriptor in DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_move_abilities:
        for source in _generic_rule_ability_sources(
            activation=activation,
            execution_records=execution_records,
            coverage_descriptor_id=descriptor.coverage_descriptor_id,
            ability_ids=descriptor.ability_ids(),
        ):
            bindings.append(
                AdvanceMoveHookBinding(
                    hook_id=descriptor.hook_id(source),
                    source_id=descriptor.source_rule_id,
                    handler=_advance_move_handler_for_descriptor(source, descriptor),
                )
            )
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _advance_move_handler_for_descriptor(
    source: GenericRuleAbilitySource,
    descriptor: GenericRuleAdvanceMoveAbility,
) -> AdvanceMoveHandler:
    def handler(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
        if type(context) is not AdvanceMoveContext:
            raise GameLifecycleError("Generic RuleIR advance move ability requires context.")
        matching_effects = generic_rule_ability_effects_for_unit(
            state=context.state,
            source=source,
            unit_instance_id=descriptor.target_unit_instance_id(context),
            ability=descriptor.ability_id,
        )
        if not matching_effects:
            return None
        if not descriptor.context_predicate(context, source, matching_effects):
            return None
        return descriptor.grant_builder(context, source, matching_effects)

    return handler


def _generic_rule_ability_sources(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[Phase17FExecutionRecord, ...],
    coverage_descriptor_id: str,
    ability_ids: tuple[str, ...],
) -> tuple[GenericRuleAbilitySource, ...]:
    if type(activation) is not RuntimeContentActivation:
        raise GameLifecycleError("Generic RuleIR ability bindings require activation.")
    if type(execution_records) is not tuple:
        raise GameLifecycleError("Generic RuleIR ability bindings require execution records.")
    selected_detachment_ids = set(activation.selected_detachment_ids)
    requested_descriptor_id = _validate_identifier(
        "coverage_descriptor_id",
        coverage_descriptor_id,
    )
    sources: list[GenericRuleAbilitySource] = []
    for record in execution_records:
        if type(record) is not Phase17FExecutionRecord:
            raise GameLifecycleError("Generic RuleIR ability bindings require execution records.")
        if not _record_is_generic_detachment_rule(record):
            continue
        if record.coverage_descriptor_id != requested_descriptor_id:
            continue
        if record.detachment_id not in selected_detachment_ids:
            continue
        rule_ir = _rule_ir_for_record(record)
        if not rule_ir_grants_any_ability(rule_ir, abilities=ability_ids):
            continue
        sources.append(GenericRuleAbilitySource(record=record, rule_ir=rule_ir))
    return tuple(sorted(sources, key=lambda source: source.record.execution_id))


def _record_is_generic_detachment_rule(record: Phase17FExecutionRecord) -> bool:
    return (
        record.coverage_kind is faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_RULE
        and record.execution_status
        is faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
    )


def _rule_ir_for_record(record: Phase17FExecutionRecord) -> RuleIR:
    rule_ir = faction_rule_ir_promotion_2026_07.current_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    _validate_record_rule_ir_hash(record=record, rule_ir=rule_ir)
    return rule_ir


def _validate_record_rule_ir_hash(
    *,
    record: Phase17FExecutionRecord,
    rule_ir: RuleIR,
) -> None:
    if record.rule_ir_hash is None:
        raise GameLifecycleError("Generic lifecycle execution record requires rule_ir_hash.")
    if rule_ir.ir_hash() != record.rule_ir_hash:
        raise GameLifecycleError("Generic lifecycle execution record has stale RuleIR hash.")
