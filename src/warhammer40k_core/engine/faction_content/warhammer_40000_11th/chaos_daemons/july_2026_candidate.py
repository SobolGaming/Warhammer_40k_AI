from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentContribution,
    combine_runtime_content_contributions,
)

from .army_rule import staged_july_runtime_contribution as army_rule_contribution
from .datasheets import runtime_contribution as datasheet_contribution
from .july_2026_updates import runtime_contribution as july_updates_contribution

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:faction_manifest:july_2026_candidate"


def runtime_contribution() -> RuntimeContentContribution:
    return combine_runtime_content_contributions(
        contribution_id=CONTRIBUTION_ID,
        contributions=(
            army_rule_contribution(),
            datasheet_contribution(),
            july_updates_contribution(),
        ),
    )
