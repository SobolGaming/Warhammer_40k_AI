from __future__ import annotations

from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:rule:scaffold"
FAR_REACHING_DOOM_SOURCE_RULE_ID = "phase17f:phase17e:aeldari:path-of-the-outcast:far-reaching-doom"
FAR_REACHING_DOOM_EFFECT_KIND = "aeldari_path_of_the_outcast_far_reaching_doom"
AELDARI_FACTION_ID = "aeldari"
PATH_OF_THE_OUTCAST_DETACHMENT_ID = "path-of-the-outcast"
RANGERS = "RANGERS"
SHROUD_RUNNERS = "SHROUD RUNNERS"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)
