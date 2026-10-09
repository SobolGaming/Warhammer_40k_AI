"""Shared Order 58 failed-save Damage-to-0 fixtures."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
    _ruleset,
    _shooting_lifecycle,
    _state,
)
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.runtime_modifiers import (
    FailedSaveDamageReplacement,
    FailedSaveDamageReplacementBinding,
    FailedSaveDamageReplacementContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.unit_factory import UnitInstance

FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE = "failed_save_damage_replaced"
ORDER58_SOURCE_ID = "order58-failed-save-source"
ORDER58_MODIFIER_ID = "order58-failed-save-replacement"


def order58_shooting_lifecycle(
    *,
    game_id: str = "order58-game",
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    return _shooting_lifecycle(alpha_unit_ids=("intercessor-1",), game_id=game_id)


def isolate_defender_model(lifecycle: GameLifecycle, defender: UnitInstance) -> None:
    state = _state(lifecycle)
    battlefield = state.battlefield_state
    assert battlefield is not None
    extra_ids = tuple(model.model_instance_id for model in defender.own_models[1:])
    if extra_ids:
        state.battlefield_state = battlefield.with_removed_models(extra_ids)


def order58_weapon(
    lifecycle: GameLifecycle,
    attacker: UnitInstance,
    *,
    profile_id: str,
    damage: int = 3,
    armor_penetration: int = 0,
    attacks: int = 1,
) -> WeaponProfile:
    return replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id=profile_id,
        attack_profile=AttackProfile.fixed(attacks),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
        armor_penetration=CharacteristicValue.from_raw(
            Characteristic.ARMOR_PENETRATION,
            armor_penetration,
        ),
        damage_profile=DamageProfile.fixed(damage),
        keywords=(WeaponKeyword.IGNORES_COVER,),
    )


def order58_replacement_binding(
    *,
    source_unit_instance_id: str,
    replacement_damage: int = 0,
) -> FailedSaveDamageReplacementBinding:
    def handler(
        context: FailedSaveDamageReplacementContext,
    ) -> FailedSaveDamageReplacement | None:
        if context.target_unit_instance_id != source_unit_instance_id:
            return None
        return FailedSaveDamageReplacement(
            source_id=ORDER58_SOURCE_ID,
            source_unit_instance_id=source_unit_instance_id,
            replacement_damage=replacement_damage,
        )

    return FailedSaveDamageReplacementBinding(
        modifier_id=ORDER58_MODIFIER_ID,
        source_id=ORDER58_SOURCE_ID,
        handler=handler,
    )


def order58_registry(
    *,
    source_unit_instance_id: str,
    replacement_damage: int = 0,
) -> RuntimeModifierRegistry:
    return RuntimeModifierRegistry.from_bindings(
        failed_save_damage_replacement_bindings=(
            order58_replacement_binding(
                source_unit_instance_id=source_unit_instance_id,
                replacement_damage=replacement_damage,
            ),
        )
    )


def order58_injected_rolls(
    *,
    sequence_id: str,
    weapon_profile: WeaponProfile,
    allocated_model_id: str,
    attacks: int,
    save_value: int,
) -> tuple[DiceRollResult, ...]:
    rolls: list[DiceRollResult] = []
    attack_ids = tuple(
        f"{sequence_id}:pool-001:attack-{index:03d}" for index in range(1, attacks + 1)
    )
    for attack_context_id, index in zip(attack_ids, range(1, attacks + 1), strict=True):
        rolls.append(
            _fixed_roll_result(
                roll_id=f"{sequence_id}-hit-{index}",
                spec=attack_sequence_hit_roll_spec(
                    weapon_profile_id=weapon_profile.profile_id,
                    attack_context_id=attack_context_id,
                    attacker_player_id="player-a",
                ),
                value=6,
            )
        )
        rolls.append(
            _fixed_roll_result(
                roll_id=f"{sequence_id}-wound-{index}",
                spec=attack_sequence_wound_roll_spec(
                    weapon_profile_id=weapon_profile.profile_id,
                    attack_context_id=attack_context_id,
                    attacker_player_id="player-a",
                ),
                value=6,
            )
        )
    for attack_context_id, index in zip(attack_ids, range(1, attacks + 1), strict=True):
        rolls.append(
            _fixed_roll_result(
                roll_id=f"{sequence_id}-save-{index}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id="player-b",
                    allocated_model_id=allocated_model_id,
                    attack_context_id=attack_context_id,
                ),
                value=save_value,
            )
        )
    return tuple(rolls)


def resolve_order58_attack(
    *,
    lifecycle: GameLifecycle,
    attacker: UnitInstance,
    defender: UnitInstance,
    sequence_id: str,
    attacks: int = 1,
    save_value: int = 1,
    armor_penetration: int = 0,
    damage: int = 3,
    registry: RuntimeModifierRegistry | None = None,
) -> None:
    isolate_defender_model(lifecycle, defender)
    defender_model = defender.own_models[0]
    weapon_profile = order58_weapon(
        lifecycle,
        attacker,
        profile_id=f"{sequence_id}-rifle",
        damage=damage,
        armor_penetration=armor_penetration,
        attacks=attacks,
    )
    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=_state(lifecycle),
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=attacks,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=order58_injected_rolls(
                sequence_id=sequence_id,
                weapon_profile=weapon_profile,
                allocated_model_id=defender_model.model_instance_id,
                attacks=attacks,
                save_value=save_value,
            ),
        ),
        runtime_modifier_registry=registry,
    )
    assert remaining_sequence is None
    assert status is None


def replacement_events(lifecycle: GameLifecycle) -> tuple[EventRecord, ...]:
    return tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == FAILED_SAVE_DAMAGE_REPLACED_EVENT_TYPE
    )


def defender_wounds(lifecycle: GameLifecycle, defender: UnitInstance) -> int:
    return model_by_id(
        state=_state(lifecycle),
        model_instance_id=defender.own_models[0].model_instance_id,
    ).current_wounds


def typed_replacement_payload(event: EventRecord) -> dict[str, object]:
    payload = event.payload
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)
