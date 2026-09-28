"""Intrinsic weapon permissions join the shared optional attack reroll authority."""

from __future__ import annotations

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.source_backed_rerolls import SourceBackedRerollPermissionContext
from warhammer40k_core.engine.weapon_abilities import TWIN_LINKED_RULE_ID, has_weapon_keyword
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def intrinsic_wound_reroll_contexts(
    *, pool: RangedAttackPool, player_id: str, roll_type: str
) -> tuple[SourceBackedRerollPermissionContext, ...]:
    if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TWIN_LINKED):
        return ()
    return (
        SourceBackedRerollPermissionContext(
            permission=RerollPermission(
                source_id=TWIN_LINKED_RULE_ID,
                timing_window=roll_type,
                owning_player_id=player_id,
                eligible_roll_type=roll_type,
                component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            ),
            source_payload={
                "effect_kind": "intrinsic_weapon_reroll",
                "source_rule_id": TWIN_LINKED_RULE_ID,
                "attacker_model_instance_id": pool.attacker_model_instance_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "weapon_source_ids": list(pool.weapon_profile.source_ids),
                "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
            },
        ),
    )
