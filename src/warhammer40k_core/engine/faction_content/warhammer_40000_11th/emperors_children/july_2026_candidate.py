from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import EnhancementDefinition
from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentContribution,
    combine_runtime_content_contributions,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
    july_faction_packs_2026_07,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)

from .manifest import runtime_contribution as june_runtime_contribution

CONTRIBUTION_ID = "warhammer_40000_11th:emperors_children:faction_manifest:july_2026_candidate"
EXALTED_PATRON_ENHANCEMENT_ID = "000010654003"


def runtime_contribution() -> RuntimeContentContribution:
    return combine_runtime_content_contributions(
        contribution_id=CONTRIBUTION_ID,
        contributions=(june_runtime_contribution(),),
    )


def faction_execution_records(
    base_records: tuple[Phase17FExecutionRecord, ...] | None = None,
) -> tuple[Phase17FExecutionRecord, ...]:
    records = (
        faction_execution_2026_27.execution_records()
        if base_records is None
        else _validate_execution_records(base_records)
    )
    successor = july_faction_packs_2026_07.exalted_patron().execution_record()
    replaced = 0
    staged_records: list[Phase17FExecutionRecord] = []
    for record in records:
        if record.execution_id == successor.execution_id:
            staged_records.append(successor)
            replaced += 1
        else:
            staged_records.append(record)
    if replaced != 1:
        raise GameLifecycleError(
            "July Emperor's Children provider requires one Exalted Patron predecessor record."
        )
    return tuple(sorted(staged_records, key=lambda record: record.execution_id))


def rule_ir_by_coverage_descriptor_id(coverage_descriptor_id: str) -> RuleIR:
    artifact = july_faction_packs_2026_07.exalted_patron()
    if coverage_descriptor_id == artifact.phase17e_descriptor_id:
        return artifact.rule_ir()
    return faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        coverage_descriptor_id
    )


def staged_army_catalog(catalog: ArmyCatalog) -> ArmyCatalog:
    if type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("July Emperor's Children provider requires ArmyCatalog.")
    artifact = july_faction_packs_2026_07.exalted_patron()
    replacements = 0
    enhancements: list[EnhancementDefinition] = []
    for enhancement in catalog.enhancements:
        if enhancement.enhancement_id != EXALTED_PATRON_ENHANCEMENT_ID:
            enhancements.append(enhancement)
            continue
        enhancements.append(
            replace(
                enhancement,
                source_id=artifact.source_row_id,
                target_required_keywords=tuple(artifact.target_required_keywords),
            )
        )
        replacements += 1
    if replacements != 1:
        raise GameLifecycleError(
            "July Emperor's Children provider requires one Exalted Patron Enhancement."
        )
    return replace(catalog, enhancements=tuple(enhancements))


def _validate_execution_records(
    records: tuple[Phase17FExecutionRecord, ...],
) -> tuple[Phase17FExecutionRecord, ...]:
    if type(records) is not tuple:
        raise GameLifecycleError(
            "July Emperor's Children provider execution records must be a tuple."
        )
    for record in records:
        if type(record) is not Phase17FExecutionRecord:
            raise GameLifecycleError(
                "July Emperor's Children provider received an invalid execution record."
            )
    return records
