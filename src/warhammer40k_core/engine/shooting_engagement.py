"""Model-scoped 10.06 and rules-unit-scoped 17.03 shooting penalties."""

from __future__ import annotations

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.weapon_abilities import has_close_quarters_weapon_keyword
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_engaged_shooting_2026_09,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_actions_2026_09 import (
    SOURCE_IDS,
)

CLOSE_QUARTERS_SHOOTING_SOURCE_ID = SOURCE_IDS[3]
ENGAGED_TARGET_SOURCE_ID = core_engaged_shooting_2026_09.ENGAGED_TARGET_SOURCE_ID


def is_monster_or_vehicle(keywords: tuple[str, ...]) -> bool:
    """Consume canonical catalog tokens without promoting unit keywords to models."""
    return "MONSTER" in keywords or "VEHICLE" in keywords


def engaged_shooting_penalty_sources(
    *,
    attacker_model_keywords: tuple[str, ...],
    attacker_engaged: bool,
    attacker_engaged_with_target: bool,
    target_keywords: tuple[str, ...],
    target_engaged: bool,
    weapon_profile: WeaponProfile,
) -> tuple[str, ...]:
    """Keep both causes until the ordinary shared hit-roll cap is applied."""
    if attacker_engaged_with_target and has_close_quarters_weapon_keyword(weapon_profile):
        return ()
    return (
        *(
            (CLOSE_QUARTERS_SHOOTING_SOURCE_ID,)
            if attacker_engaged and is_monster_or_vehicle(attacker_model_keywords)
            else ()
        ),
        *(
            (ENGAGED_TARGET_SOURCE_ID,)
            if target_engaged and is_monster_or_vehicle(target_keywords)
            else ()
        ),
    )
