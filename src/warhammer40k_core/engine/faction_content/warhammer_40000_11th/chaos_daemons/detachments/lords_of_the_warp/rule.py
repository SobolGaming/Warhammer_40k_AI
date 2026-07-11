from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_lords_of_the_warp_ir_support_2026_27 as lords_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:lords_of_the_warp:rule"

LORDS_OF_THE_WARP_DETACHMENT_ID = lords_ir.LORDS_OF_THE_WARP_DETACHMENT_ID
LEGIONES_DAEMONICA = lords_ir.LEGIONES_DAEMONICA_KEYWORD
CHARACTER = lords_ir.CHARACTER_KEYWORD
MONSTER = lords_ir.MONSTER_KEYWORD
KHORNE = lords_ir.KHORNE_KEYWORD
NURGLE = lords_ir.NURGLE_KEYWORD
SLAANESH = lords_ir.SLAANESH_KEYWORD
TZEENTCH = lords_ir.TZEENTCH_KEYWORD


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
