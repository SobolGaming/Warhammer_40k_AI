"""Canonical attack fixtures for the Order 43 threshold invariant."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
    _shooting_lifecycle,
    _state,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.attack_sequence import HitRoll, attack_sequence_hit_roll_spec
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.weapon_abilities import (
    FIRE_OVERWATCH_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession


def hit_roll(
    *,
    raw: int,
    mode: str = "normal",
    threshold: int = 4,
    modifier: int = 0,
    status: str = "critical_hit_threshold",
    explicit_snap: bool = False,
    abilities: tuple[AbilityDescriptor, ...] = (),
    torrent: bool = False,
    keywords: tuple[WeaponKeyword, ...] = (),
    phase: BattlePhase = BattlePhase.SHOOTING,
) -> HitRoll:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker, defender = units["intercessor-1"], units["enemy"]
    parameters: dict[str, JsonValue] = {
        "attack_role": "attacker",
        "roll_type": "hit",
        "status": status,
        "critical_threshold"
        if status == "critical_hit_threshold"
        else "minimum_unmodified_success": threshold,
    }
    targeting = {
        "normal": (),
        "snap": (SNAP_SHOOTING_RULE_ID,),
        "overwatch": (FIRE_OVERWATCH_RULE_ID,),
        "indirect": (INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,),
        "observed_indirect": (
            INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
            INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
        ),
    }[mode]
    if explicit_snap:
        parameters["required_targeting_rule_id"] = (
            FIRE_OVERWATCH_RULE_ID if mode == "overwatch" else SNAP_SHOOTING_RULE_ID
        )
    state.record_persisting_effect(
        generic_effect(
            effect_id="order43:threshold",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters=parameters,
        )
    )
    profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 5),
        keywords=(WeaponKeyword.TORRENT,) if torrent else keywords,
        abilities=abilities,
    )
    pool = replace(
        _attack_pool_for_test(
            attacker=attacker, defender=defender, weapon_profile=profile, attacks=1
        ),
        targeting_rule_ids=targeting,
        hit_roll_modifier=modifier,
        hit_roll_modifiers=(
            RollModifier("order43:modifier", modifier, source_id="order43:modifier-source"),
        )
        if modifier
        else (),
    )
    forbidden = (
        (SNAP_SHOOTING_RULE_ID,)
        if mode in {"snap", "overwatch"}
        else (INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,)
        if "indirect" in mode
        else ()
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id,
        attack_context_id="order43:attack",
        attacker_player_id="player-a",
        reroll_forbidden_rule_ids=forbidden,
    )
    manager = DiceRollManager(
        "order43",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(_fixed_roll_result(roll_id="order43:hit", spec=spec, value=raw),),
    )
    return _roll_hit(
        state=state,
        manager=manager,
        pool=pool,
        attacker_player_id="player-a",
        attack_context_id="order43:attack",
        source_phase=phase,
    )


def critical_hit_session(*, phase: BattlePhase = BattlePhase.SHOOTING) -> LocalGameSession:
    """Real Shooting activation and a canonical persisted Fight threshold fixture."""
    from tests.phase13b_shooting_declaration_helpers import (
        _canonical_catalog,
        _compact_intercessor_catalog,
    )
    from tests.phase15c_fight_order_helpers import fight_lifecycle
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.detachment import StratagemDefinition
    from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_stratagem_activation_2026_27 as activation,
    )

    profile = next(
        row
        for row in activation.stratagem_activation_profiles()
        if row.stratagem_id == "000009746003"
    )
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    detachment = replace(
        catalog.detachments[0],
        detachment_id=profile.detachment_id,
        name="Threshold consumer fixture",
        stratagem_ids=(profile.stratagem_id,),
    )
    catalog = replace(
        catalog,
        detachments=(*catalog.detachments, detachment),
        stratagems=(
            *catalog.stratagems,
            StratagemDefinition(
                stratagem_id=profile.stratagem_id,
                name=profile.name,
                source_id=profile.source_id,
                command_point_cost=profile.command_point_cost,
            ),
        ),
        wargear=tuple(
            replace(
                row,
                weapon_profiles=tuple(
                    replace(
                        weapon,
                        skill=CharacteristicValue.from_raw(weapon.skill.characteristic, 6),
                        attack_profile=AttackProfile.fixed(12),
                        damage_profile=DamageProfile.fixed(1),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                        keywords=(WeaponKeyword.LETHAL_HITS, WeaponKeyword.SUSTAINED_HITS),
                        abilities=(
                            AbilityDescriptor.sustained_hits(1),
                            AbilityDescriptor.lethal_hits(),
                        ),
                    )
                    for weapon in row.weapon_profiles
                ),
            )
            for row in catalog.wargear
        ),
    )
    if phase is BattlePhase.SHOOTING:
        lifecycle, _ = _shooting_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            catalog=catalog,
            alpha_unit_specs=(
                ("intercessor-1", "core-intercessor-like-infantry", "core-intercessor-like", 1),
            ),
            enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", 5),
            enemy_pose=Pose.at(30, 35),
            alpha_detachment_ids=(profile.detachment_id,),
            game_id="order43-facade",
        )
    else:
        lifecycle, _ = fight_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            enemy_unit_ids=("enemy",),
            origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
            game_id="order43-facade-fight",
            model_count=1,
            catalog=catalog,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            fights_first_unit_keys=("intercessor-1",),
            alpha_detachment_ids=(profile.detachment_id,),
        )
    state = lifecycle.state
    assert state is not None
    if phase is BattlePhase.FIGHT:
        from typing import cast

        from warhammer40k_core.engine.effects import EffectExpiration

        effect = generic_effect(
            effect_id="order43:fight-threshold",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-1",),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "status": "critical_hit_threshold",
                "critical_threshold": 5,
                "roll_type": "hit",
                "attack_role": "attacker",
            },
        )
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        context = cast(dict[str, JsonValue], payload["context"])
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=phase,
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=phase, player_id="player-a"
                ),
                effect_payload={**payload, "context": {**context, "phase": phase.value}},
            )
        )
    state.gain_command_points(
        player_id="player-a",
        amount=2,
        source_id="fixture-starting-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
