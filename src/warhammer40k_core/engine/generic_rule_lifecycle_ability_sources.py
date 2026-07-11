from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.generic_rule_ability_effects import rule_ir_grants_any_ability
from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord
_validate_identifier = IdentifierValidator(GameLifecycleError)


def generic_rule_ability_sources(
    *,
    activation: RuntimeContentActivation,
    execution_records: tuple[_Phase17FExecutionRecord, ...],
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
        if type(record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic RuleIR ability bindings require execution records.")
        if record.execution_status is not (
            faction_execution_2026_27.Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        ):
            continue
        if record.coverage_kind not in (
            faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_RULE,
            faction_coverage_2026_27.Phase17ECoverageKind.DETACHMENT_STRATAGEM,
        ):
            continue
        if record.coverage_descriptor_id != requested_descriptor_id:
            continue
        if record.detachment_id not in selected_detachment_ids:
            continue
        rule_ir = _rule_ir_for_record(record)
        if rule_ir_grants_any_ability(rule_ir, abilities=ability_ids):
            sources.append(GenericRuleAbilitySource(record=record, rule_ir=rule_ir))
    return tuple(sorted(sources, key=lambda source: source.record.execution_id))


def _rule_ir_for_record(record: _Phase17FExecutionRecord) -> RuleIR:
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    _validate_record_rule_ir_hash(record=record, rule_ir=rule_ir)
    return rule_ir


def _validate_record_rule_ir_hash(*, record: _Phase17FExecutionRecord, rule_ir: RuleIR) -> None:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic lifecycle record requires RuleIR.")
    if record.rule_ir_hash is None:
        raise GameLifecycleError("Generic lifecycle execution record requires rule_ir_hash.")
    try:
        actual_hash = rule_ir.ir_hash()
    except RuleIRError as exc:
        raise GameLifecycleError("Generic lifecycle RuleIR hash failed.") from exc
    if actual_hash != record.rule_ir_hash:
        raise GameLifecycleError("Generic lifecycle RuleIR hash drift.")
