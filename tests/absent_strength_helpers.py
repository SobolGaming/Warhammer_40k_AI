"""Canonical attack hosts for Core 02.04.01 Strength interactions."""

from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _compact_shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose


def strength_session(
    phase: BattlePhase,
    *,
    strength: int | None = None,
    twin_linked: bool = True,
    command_reroll: bool = False,
) -> LocalGameSession:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    value = (
        CharacteristicValue.source_dash(Characteristic.STRENGTH)
        if strength is None
        else CharacteristicValue.from_raw(Characteristic.STRENGTH, strength)
    )
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        strength=value,
                        attack_profile=AttackProfile.fixed(12),
                        keywords=(WeaponKeyword.TORRENT,)
                        + ((WeaponKeyword.TWIN_LINKED,) if twin_linked else ()),
                        abilities=(),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        model,
                        characteristics=tuple(
                            CharacteristicValue.from_raw(Characteristic.TOUGHNESS, 1)
                            if characteristic.characteristic is Characteristic.TOUGHNESS
                            else characteristic
                            for characteristic in model.characteristics
                        ),
                    )
                    for model in sheet.model_profiles
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    if phase is BattlePhase.SHOOTING:
        lifecycle, _ = _compact_shooting_lifecycle(catalog=catalog, game_id="order88-shooting")
    else:
        lifecycle, _ = fight_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            enemy_unit_ids=("enemy",),
            origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
            game_id="order88-fight",
            model_count=1,
            catalog=catalog,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            fights_first_unit_keys=("intercessor-1",),
            record_deployment=True,
        )
    state = lifecycle.state
    assert state is not None
    if command_reroll:
        from warhammer40k_core.engine.command_points import CommandPointSourceKind

        state.gain_command_points(
            player_id="player-a",
            amount=1,
            source_id="fixture:order88",
            source_kind=CommandPointSourceKind.OTHER,
        )
    effect = generic_effect(
        effect_id="order88-strength-comparison",
        owner_player_id="player-b",
        target_unit_instance_ids=("army-beta:enemy",),
        target_kind="this_unit",
        effect_kind="modify_dice_roll",
        parameters={
            "roll_type": "wound",
            "delta": -1,
            "target_constraint": "attack_strength_greater_than_target_toughness",
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
    return LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
