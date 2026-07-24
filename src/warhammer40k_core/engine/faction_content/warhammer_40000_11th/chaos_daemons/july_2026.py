from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution

from .july_2026_candidate import runtime_contribution as candidate_runtime_contribution

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:faction_manifest:july_2026"


def runtime_contribution() -> RuntimeContentContribution:
    return candidate_runtime_contribution().with_contribution_id(CONTRIBUTION_ID)


__all__ = ("CONTRIBUTION_ID", "runtime_contribution")
