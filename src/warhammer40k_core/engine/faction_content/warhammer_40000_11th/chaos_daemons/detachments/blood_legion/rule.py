from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:rule"
MURDERCALL_HOOK_ID = blood_legion_ir.MURDERCALL_HOOK_ID
BLOOD_TAINTED_HOOK_ID = blood_legion_ir.BLOOD_TAINTED_HOOK_ID
SOURCE_RULE_ID = blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID
CHAOS_DAEMONS_FACTION_ID = blood_legion_ir.CHAOS_DAEMONS_FACTION_ID
BLOOD_LEGION_DETACHMENT_ID = blood_legion_ir.BLOOD_LEGION_DETACHMENT_ID
LEGIONES_DAEMONICA = blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD
KHORNE = blood_legion_ir.KHORNE_KEYWORD
AIRCRAFT = blood_legion_ir.AIRCRAFT_KEYWORD
MURDERCALL_RANGE_INCHES = blood_legion_ir.MURDERCALL_RANGE_INCHES


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
