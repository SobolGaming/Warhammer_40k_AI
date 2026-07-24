from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import (
    RuntimeContentContribution,
    combine_runtime_content_contributions,
)

from .july_2026_updates import runtime_contribution as july_updates_contribution
from .manifest import runtime_contribution as june_runtime_contribution

CONTRIBUTION_ID = "warhammer_40000_11th:thousand_sons:faction_manifest:july_2026_candidate"


def runtime_contribution() -> RuntimeContentContribution:
    return combine_runtime_content_contributions(
        contribution_id=CONTRIBUTION_ID,
        contributions=(june_runtime_contribution(), july_updates_contribution()),
    )
