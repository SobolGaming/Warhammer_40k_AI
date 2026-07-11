from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_warptide_ir_support_2026_27 as warptide_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:warptide:rule"
CHAOS_DAEMONS_FACTION_ID = warptide_ir.CHAOS_DAEMONS_FACTION_ID
WARPTIDE_DETACHMENT_ID = warptide_ir.WARPTIDE_DETACHMENT_ID
WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID = warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
SOURCE_RULE_ID = warptide_ir.WARPTIDE_SOURCE_RULE_ID
RULE_IR_SOURCE_ID = (
    f"{warptide_ir.SOURCE_PACKAGE_ID}:{warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID}:"
    "source-text"
)
LEGIONES_DAEMONICA = warptide_ir.LEGIONES_DAEMONICA_KEYWORD
BATTLELINE = warptide_ir.BATTLELINE_KEYWORD
PINK_HORRORS = warptide_ir.PINK_HORRORS_KEYWORD
SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID = warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID
SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID = warptide_ir.SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
