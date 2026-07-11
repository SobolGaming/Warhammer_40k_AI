from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_lords_of_the_warp_ir_support_2026_27 as lords_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:lords_of_the_warp:enhancements"

SWOLLEN_WITH_POWER_ENHANCEMENT_ID = lords_ir.SWOLLEN_WITH_POWER_ENHANCEMENT_ID


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
