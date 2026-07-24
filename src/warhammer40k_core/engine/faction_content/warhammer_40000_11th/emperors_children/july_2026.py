from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution

from .july_2026_candidate import (
    runtime_contribution as candidate_runtime_contribution,
)
from .july_2026_candidate import (
    staged_army_catalog,
)

CONTRIBUTION_ID = "warhammer_40000_11th:emperors_children:faction_manifest:july_2026"


def runtime_contribution() -> RuntimeContentContribution:
    return candidate_runtime_contribution().with_contribution_id(CONTRIBUTION_ID)


def current_army_catalog(catalog: ArmyCatalog) -> ArmyCatalog:
    return staged_army_catalog(catalog)


__all__ = ("CONTRIBUTION_ID", "current_army_catalog", "runtime_contribution")
