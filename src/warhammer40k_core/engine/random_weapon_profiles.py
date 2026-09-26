"""Per-weapon characteristic evaluation at an explicit attack occurrence."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_random_profiles_2026_09 as random_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def evaluate_attack_weapon_profile(
    *,
    pool: RangedAttackPool,
    decisions: DecisionController,
    manager: DiceRollManager | None,
    attack_context_id: str,
    player_id: str,
    characteristics: tuple[Characteristic, ...],
) -> RangedAttackPool:
    profile = pool.weapon_profile
    replacements: dict[str, RandomProfileValue] = {}
    for field, value in (
        ("skill", profile.skill),
        ("strength", profile.strength),
        ("armor_penetration", profile.armor_penetration),
    ):
        if not isinstance(value, RandomProfileValue) or value.characteristic not in characteristics:
            continue
        scope = f"{attack_context_id}:{pool.weapon_instance_id}:{value.characteristic.value}"
        context = {
            "source_rule_id": random_source.RANDOM_PROFILES_SOURCE_ID,
            "scope_id": scope,
            "attack_context_id": attack_context_id,
            "target_unit_instance_id": pool.target_unit_instance_id,
            "wargear_id": pool.wargear_id,
            "player_id": player_id,
            "model_instance_id": pool.attacker_model_instance_id,
            "weapon_instance_id": pool.weapon_instance_id,
            "weapon_profile_id": pool.weapon_profile_id,
            "descriptor": replace(value, evaluation=None, evaluation_id=None).to_payload(),
        }
        previous = [
            event.payload
            for event in decisions.event_log.records
            if event.event_type == "random_weapon_profile_evaluated"
            and isinstance(event.payload, dict)
            and event.payload.get("scope_id") == scope
        ]
        if previous:
            if len(previous) != 1:
                raise GameLifecycleError("Random weapon evaluation occurrence is duplicated.")
            payload = previous[0]
            if canonical_json({k: v for k, v in payload.items() if k != "roll"}) != canonical_json(
                context
            ):
                raise GameLifecycleError("Random weapon evaluation descriptor or context drifted.")
            roll_payload = payload.get("roll")
            if not isinstance(roll_payload, dict):
                raise GameLifecycleError("Random weapon evaluation dice evidence is missing.")
            roll = RandomCharacteristicRoll.from_payload(
                cast(RandomCharacteristicRollPayload, roll_payload)
            )
        else:
            if manager is None:
                raise GameLifecycleError(
                    "Random weapon value is unresolved for this attack occurrence."
                )
            roll = manager.roll_random_characteristic(
                characteristic=value.characteristic,
                timing=RandomCharacteristicTiming.PER_WEAPON,
                scope_id=scope,
                expression=value.expression,
                reason=f"Weapon profile {value.characteristic.value}",
                actor_id=player_id,
            )
            decisions.event_log.append(
                "random_weapon_profile_evaluated", {**context, "roll": roll.to_payload()}
            )
        replacements[field] = value.evaluate(
            raw=roll.value, evaluation_id=scope, target_id=pool.weapon_instance_id
        )
    if not replacements:
        return pool
    return replace(
        pool,
        weapon_profile=replace(
            profile,
            skill=replacements.get("skill", profile.skill),
            strength=replacements.get("strength", profile.strength),
            armor_penetration=replacements.get("armor_penetration", profile.armor_penetration),
        ),
    )


def random_melee_pool_evidence(
    pools: tuple[RangedAttackPool, ...], *, state: GameState
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    random_defence = any(
        isinstance(value, RandomProfileValue)
        and value.characteristic
        in {
            Characteristic.TOUGHNESS,
            Characteristic.WOUNDS,
            Characteristic.SAVE,
            Characteristic.INVULNERABLE_SAVE,
        }
        for unit_id in {pool.target_unit_instance_id for pool in pools}
        for model in rules_unit_view_by_id(state=state, unit_instance_id=unit_id).alive_models()
        for value in model.characteristics
    )
    if not random_defence and not any(
        isinstance(value, RandomProfileValue)
        for pool in pools
        for value in (
            pool.weapon_profile.skill,
            pool.weapon_profile.strength,
            pool.weapon_profile.armor_penetration,
        )
    ):
        return {}
    return {"attack_pools": validate_json_value([pool.to_payload() for pool in pools])}
