"""Real profile thresholds through live hit, wound and target-distance consumers."""

import pytest

from tests.support.section02_consumers import attack_pool, combat_state, scenario, set_origin
from tests.support.section02_fixtures import INFRACTORS, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _roll_wound
from warhammer40k_core.engine.attack_sequence_model import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.interpreted_dice import CriticalRollThreshold
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model


@pytest.mark.parametrize(
    ("wargear", "phase"),
    [("bolt-pistol", BattlePhase.SHOOTING), ("duelling-sabre", BattlePhase.FIGHT)],
)
@pytest.mark.parametrize(
    ("roll", "success"), [(1, False), (2, False), (3, True), (4, True), (6, True)]
)
def test_02_04_bs_and_ws_are_live_hit_thresholds(
    section02_definitions: Section02Definitions,
    wargear: str,
    phase: BattlePhase,
    roll: int,
    success: bool,
) -> None:
    attacker = section02_definitions.unit(identity="attacker")
    target = section02_definitions.unit(identity="target", army_id="opponent-army")
    weapon = section02_definitions.weapon(f"{INFRACTORS}:{wargear}")
    state = combat_state(section02_definitions, attacker, target)
    pool = attack_pool(attacker, target, weapon, f"{INFRACTORS}:{wargear}")
    manager = DiceRollManager("hit-boundary")
    manager.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id=weapon.profile_id,
            attack_context_id="attack",
            attacker_player_id="owner",
        ),
        (roll,),
    )
    result = _roll_hit(
        state=state,
        manager=manager,
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="attack",
        source_phase=phase,
    )
    assert result.target_number == 3
    assert result.successful is success


@pytest.mark.parametrize(("roll", "success"), [(1, False), (3, False), (4, True), (6, True)])
def test_02_04_strength_is_consumed_by_wound_rolls(
    section02_definitions: Section02Definitions, roll: int, success: bool
) -> None:
    attacker = section02_definitions.unit(identity="attacker")
    target = section02_definitions.unit(identity="target", army_id="opponent-army")
    weapon = section02_definitions.weapon(f"{INFRACTORS}:bolt-pistol")
    pool = attack_pool(attacker, target, weapon, f"{INFRACTORS}:bolt-pistol")
    manager = DiceRollManager("wound-boundary")
    manager.roll_fixed(
        attack_sequence_wound_roll_spec(
            weapon_profile_id=weapon.profile_id,
            attack_context_id="attack",
            attacker_player_id="owner",
        ),
        (roll,),
    )
    result = _roll_wound(
        manager=manager,
        pool=pool,
        toughness=target.own_models[0].characteristic(Characteristic.TOUGHNESS).final,
        attacker_player_id="owner",
        attack_context_id="attack",
        critical_threshold=CriticalRollThreshold(),
    )
    assert result.target_number == 4
    assert result.successful is success


@pytest.mark.parametrize(
    ("edge_distance", "in_range"), [(11.99, True), (12.0, True), (12.01, False)]
)
def test_02_04_actual_pistol_range_bounds_targets(
    section02_definitions: Section02Definitions, edge_distance: float, in_range: bool
) -> None:
    attacker = section02_definitions.unit(identity="attacker")
    target = section02_definitions.unit(identity="target", army_id="opponent-army")
    weapon = section02_definitions.weapon(f"{INFRACTORS}:bolt-pistol")
    state = combat_state(section02_definitions, attacker, target)
    # Both actual Infractor bases are32mm circles; place target wholly beyond shooter.
    set_origin(state, attacker, 10, 10)
    set_origin(state, target, 10 + edge_distance + 32 / 25.4, 10)
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=weapon,
        target_unit_id=target.unit_instance_id,
    )
    assert bool(result.target_in_range_model_ids) is in_range
