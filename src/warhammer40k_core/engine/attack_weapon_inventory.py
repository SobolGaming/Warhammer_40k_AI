"""Build the source inventory before any Select Weapons instance choice."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.weapon_selection_context import WeaponSelectionContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import RulesUnitView


def shooting_weapon_selection_targets(
    *, state: GameState, player_id: str, required_target_ids: tuple[str, ...]
) -> tuple[RulesUnitView, ...]:
    """Resolve target identity once for a request or declaration validation pass."""
    from warhammer40k_core.engine.phases.shooting_validation import _enemy_placed_unit_ids
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    target_ids = sorted(
        {*required_target_ids, *_enemy_placed_unit_ids(state=state, player_id=player_id)}
    )
    return tuple(
        rules_unit_view_by_id(state=state, unit_instance_id=target_id) for target_id in target_ids
    )


def shooting_weapon_selection_context(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    weapon_instance_id: str,
    source_request_id: str,
    target_units: tuple[RulesUnitView, ...],
    player_id: str,
    profile: WeaponProfile,
) -> WeaponSelectionContext:
    from warhammer40k_core.engine.ranged_rule_effects import (
        weapon_profile_with_character_target_ap_effects,
    )

    target_profiles: list[tuple[str, WeaponProfile]] = []
    for target in target_units:
        target_id = target.unit_instance_id
        candidate = weapon_profile_with_character_target_ap_effects(
            profile,
            state.persisting_effects_for_unit(attacking_unit_instance_id),
            owner_player_id=player_id,
            target_keywords=target.keywords,
        )
        candidate = runtime_modifier_registry.modified_weapon_profile(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=attacking_unit_instance_id,
                attacker_model_instance_id=attacker_model_instance_id,
                target_unit_instance_id=target_id,
                weapon_profile=candidate,
            )
        )
        target_profiles.append((target_id, candidate))
    return WeaponSelectionContext(
        weapon_instance_id=weapon_instance_id,
        source_request_id=source_request_id,
        target_profiles=tuple(target_profiles),
    )


def melee_weapon_selection_context(
    *,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    weapon_instance_id: str,
    source_request_id: str,
    target_unit_instance_ids: tuple[str, ...],
    profile: WeaponProfile,
) -> WeaponSelectionContext:
    from warhammer40k_core.engine.fight_resolution import (
        _epic_challenge_profile_if_applicable,
        _modified_melee_weapon_profile,
    )

    profile = _epic_challenge_profile_if_applicable(
        state=state,
        unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        profile=profile,
    )
    return WeaponSelectionContext(
        weapon_instance_id=weapon_instance_id,
        source_request_id=source_request_id,
        target_profiles=tuple(
            (
                target_id,
                _modified_melee_weapon_profile(
                    state=state,
                    runtime_modifier_registry=runtime_modifier_registry,
                    attacking_unit_instance_id=attacking_unit_instance_id,
                    attacker_model_instance_id=attacker_model_instance_id,
                    target_unit_instance_id=target_id,
                    profile=profile,
                ),
            )
            for target_id in target_unit_instance_ids
        ),
    )
