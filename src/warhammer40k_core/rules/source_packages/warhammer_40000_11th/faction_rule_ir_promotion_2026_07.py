from __future__ import annotations

from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27,
    july_faction_packs_2026_07,
)


def current_rule_ir_by_coverage_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIR:
    artifact = july_faction_packs_2026_07.exalted_patron()
    if coverage_descriptor_id == artifact.phase17e_descriptor_id:
        return artifact.rule_ir()
    return faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        coverage_descriptor_id
    )


__all__ = ("current_rule_ir_by_coverage_descriptor_id",)
