from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_warptide_ir_support_2026_27 as warptide_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:warptide:enhancements"
BANE_FORGED_WEAPONS_ENHANCEMENT_ID = warptide_ir.BANE_FORGED_WEAPONS_ENHANCEMENT_ID
BANE_FORGED_WEAPONS_SOURCE_RULE_ID = warptide_ir.BANE_FORGED_WEAPONS_SOURCE_RULE_ID
BANE_FORGED_WEAPONS_RULE_IR_SOURCE_ID = (
    f"{warptide_ir.SOURCE_PACKAGE_ID}:{warptide_ir.BANE_FORGED_WEAPONS_DESCRIPTOR_ID}:source-text"
)
SOUL_HUNGRY_SLAUGHTERERS_ENHANCEMENT_ID = warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_ENHANCEMENT_ID
SOUL_HUNGRY_SLAUGHTERERS_SOURCE_RULE_ID = warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_SOURCE_RULE_ID
SOUL_HUNGRY_SLAUGHTERERS_RULE_IR_SOURCE_ID = (
    f"{warptide_ir.SOURCE_PACKAGE_ID}:{warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID}:"
    "source-text"
)
SOUL_HUNGRY_SLAUGHTERERS_COST_MODIFIER_ID = warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_MODIFIER_ID


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
