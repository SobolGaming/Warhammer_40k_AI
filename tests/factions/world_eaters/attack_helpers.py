"""Single real attack through shared resolution with explicit physical dice."""

from dataclasses import replace

from tests.factions.world_eaters.gameplay_helpers import ENEMY, SOURCE
from tests.factions.world_eaters.world_eaters_helpers import (
    _attack_pool_for_world_eaters_test,
    _fixed_roll_result,
    _runtime_content_bundle,
    _unit_by_id,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.weapon_profiles import DamageProfile, RangeProfile, WeaponKeyword
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec


def resolve_native_attack(
    session: LocalGameSession,
    *,
    incoming: bool = False,
    ranged: bool = False,
    trigger: int | None = None,
    damage: int | None = None,
    controller: DecisionController | None = None,
) -> tuple[AttackSequence | None, LifecycleStatus | None]:
    state = session.lifecycle.state
    assert state is not None
    attacker = _unit_by_id(state, ENEMY if incoming else SOURCE)
    target = _unit_by_id(state, SOURCE if incoming else ENEMY)
    player = "player-b" if incoming else "player-a"
    decisions = session.lifecycle.decision_controller if controller is None else controller
    config = session.lifecycle.config
    assert config is not None
    profile = next(
        item for item in config.army_catalog.wargear if item.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]
    if ranged:
        profile = replace(
            profile,
            range_profile=RangeProfile.distance(24),
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
        )
    if damage is not None:
        profile = replace(profile, damage_profile=DamageProfile.fixed(damage))
    registry = _runtime_content_bundle(session.lifecycle).runtime_modifier_registry
    profile = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING if ranged else BattlePhase.FIGHT,
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=profile,
        )
    )
    sequence = AttackSequence.start(
        sequence_id="we-gameplay-native",
        attacker_player_id=player,
        attacking_unit_instance_id=attacker.unit_instance_id,
        source_phase=BattlePhase.SHOOTING if ranged else BattlePhase.FIGHT,
        attack_pools=(
            _attack_pool_for_world_eaters_test(
                attacker=attacker,
                defender=target,
                weapon_profile=profile,
                attacks=1,
            ),
        ),
    )
    context = sequence.attack_context_id()
    hit = attack_sequence_hit_roll_spec(
        weapon_profile_id=profile.profile_id, attack_context_id=context, attacker_player_id=player
    )
    rolls = [_fixed_roll_result(roll_id="we-native-hit", spec=hit, value=6)]
    wound = attack_sequence_wound_roll_spec(
        weapon_profile_id=profile.profile_id, attack_context_id=context, attacker_player_id=player
    )
    rolls.append(_fixed_roll_result(roll_id="we-native-wound", spec=wound, value=6))
    if WeaponKeyword.DEVASTATING_WOUNDS not in profile.keywords:
        save = saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-a" if incoming else "player-b",
            allocated_model_id=target.own_models[0].model_instance_id,
            attack_context_id=context,
        )
        rolls.append(_fixed_roll_result(roll_id="we-native-save", spec=save, value=1))
    if trigger is not None:
        spec = DiceRollSpec(
            expression=DiceExpression(1, 6),
            reason="Destruction reaction trigger",
            roll_type="world_eaters_total_carnage",
            actor_id="player-a",
        )
        rolls.append(_fixed_roll_result(roll_id="we-native-trigger", spec=spec, value=trigger))
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log, injected_results=rolls)
    remaining, _allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=manager,
        runtime_modifier_registry=registry,
    )
    return remaining, status
