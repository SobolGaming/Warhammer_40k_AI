from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution

CONTRIBUTION_ID = (
    "warhammer_40000_11th:emperors_children:detachment:court_of_the_phoenician:enhancements:rule_ir"
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
