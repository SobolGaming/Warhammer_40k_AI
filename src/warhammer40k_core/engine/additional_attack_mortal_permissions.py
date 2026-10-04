"""Source-provider permission for the Core successful-wound attack seam.

Providers own source eligibility and conditional grants. This module neither
loads a faction rule nor derives permissions from a rule's display name.
"""

from __future__ import annotations

from typing import cast

from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.ability_damage_context import (
    ABILITY_DAMAGE_SOURCE_KEY,
    ability_damage_is_psychic_attack,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.ability_damage_source import AbilityDamageSource

ADDITIONAL_ATTACK_MORTAL_PERMISSION_KIND = "additional_attack_mortal_permission"
ADDITIONAL_ATTACK_MORTAL_SOURCE_KIND = "additional_attack_mortal_wounds"


def additional_attack_mortal_permission_effect(
    *,
    state: GameState,
    effect_id: str,
    source_rule_id: str,
    source_model_instance_id: str,
    occasion_id: str,
    mortal_wounds: int,
    weapon_scope: str,
    ability_damage_source: AbilityDamageSource | None = None,
) -> PersistingEffect:
    """Build a phase-bound source grant; only the engine records the returned effect."""
    unit_id = state.unit_instance_id_for_model(source_model_instance_id)
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    phase = state.current_battle_phase
    turn_player_id = state.active_player_id
    if phase is None or turn_player_id is None:
        raise GameLifecycleError("Additional attack mortals require a current phase and turn.")
    if source_model_instance_id not in {m.model_instance_id for m in unit.alive_models()}:
        raise GameLifecycleError("Additional attack mortals require a living source model.")
    if ability_damage_source is not None and (
        type(ability_damage_source) is not AbilityDamageSource
        or ability_damage_source.source_rule_id != source_rule_id
    ):
        raise GameLifecycleError("Additional attack ability damage source identity drifted.")
    effect = PersistingEffect(
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id=unit.owner_player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=state.battle_round,
        started_phase=phase,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round, phase=phase, player_id=turn_player_id
        ),
        effect_payload={
            "effect_kind": ADDITIONAL_ATTACK_MORTAL_PERMISSION_KIND,
            "source_model_instance_id": source_model_instance_id,
            "occasion_id": occasion_id,
            "weapon_scope": weapon_scope,
            "mortal_wounds": mortal_wounds,
            "turn_player_id": turn_player_id,
            **(
                {}
                if ability_damage_source is None
                else {
                    ABILITY_DAMAGE_SOURCE_KEY: cast(JsonValue, ability_damage_source.to_payload())
                }
            ),
        },
    )
    validate_additional_attack_mortal_permission(effect)
    return effect


def validate_additional_attack_mortal_permission(effect: PersistingEffect) -> dict[str, JsonValue]:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Additional attack mortal permission must be a typed effect.")
    payload = effect.effect_payload
    keys = {
        "effect_kind",
        "source_model_instance_id",
        "occasion_id",
        "weapon_scope",
        "mortal_wounds",
        "turn_player_id",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) not in (keys, keys | {ABILITY_DAMAGE_SOURCE_KEY})
        or payload["effect_kind"] != ADDITIONAL_ATTACK_MORTAL_PERMISSION_KIND
        or type(payload["mortal_wounds"]) is not int
        or payload["mortal_wounds"] < 1
        or payload["weapon_scope"] not in ("all", "melee", "ranged")
        or len(effect.target_unit_instance_ids) != 1
        or effect.started_phase is None
    ):
        raise GameLifecycleError("Additional attack mortal permission schema drift.")
    if ABILITY_DAMAGE_SOURCE_KEY in payload:
        ability_damage_is_psychic_attack(
            {
                "source_rule_id": effect.source_rule_id,
                ABILITY_DAMAGE_SOURCE_KEY: payload[ABILITY_DAMAGE_SOURCE_KEY],
            }
        )
    for key in ("source_model_instance_id", "occasion_id", "turn_player_id"):
        value = payload[key]
        if type(value) is not str or not value.strip() or value != value.strip():
            raise GameLifecycleError(f"Additional attack mortal permission {key} is invalid.")
    if effect.expiration != EffectExpiration.end_phase(
        battle_round=effect.started_battle_round,
        phase=effect.started_phase,
        player_id=cast(str, payload["turn_player_id"]),
    ):
        raise GameLifecycleError("Additional attack mortal permission duration drift.")
    return payload


def additional_attack_mortal_permissions(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
    attacker_player_id: str,
    attacker_model_instance_id: str,
    source_phase: BattlePhase,
    weapon_profile: WeaponProfile,
) -> tuple[PersistingEffect, ...]:
    unit = rules_unit_view_by_id(state=state, unit_instance_id=attacking_unit_instance_id)
    permissions: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != (
            ADDITIONAL_ATTACK_MORTAL_PERMISSION_KIND
        ):
            continue
        payload = validate_additional_attack_mortal_permission(effect)
        source_id = cast(str, payload["source_model_instance_id"])
        source_unit_id = state.unit_instance_id_for_model(source_id)
        if (
            effect.target_unit_instance_ids != (source_unit_id,)
            or effect.owner_player_id
            != rules_unit_view_by_id(state=state, unit_instance_id=source_unit_id).owner_player_id
        ):
            raise GameLifecycleError("Additional attack mortal permission ownership drift.")
        if (
            source_unit_id not in unit.component_unit_instance_ids
            or source_id != attacker_model_instance_id
            or effect.owner_player_id != attacker_player_id
            or effect.started_battle_round != state.battle_round
            or effect.started_phase is not state.current_battle_phase
            or payload["turn_player_id"] != state.active_player_id
        ):
            continue
        scope = payload["weapon_scope"]
        is_melee = weapon_profile.range_profile.kind is RangeProfileKind.MELEE
        if scope == "melee" and (not is_melee or source_phase is not BattlePhase.FIGHT):
            continue
        if scope == "ranged" and (is_melee or source_phase is not BattlePhase.SHOOTING):
            continue
        permissions.append(effect)
    return tuple(sorted(permissions, key=lambda effect: effect.effect_id))
