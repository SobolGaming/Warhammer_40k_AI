"""FAQs55/56: explicit threshold contracts at the live hit evaluator on native units."""

from dataclasses import replace

import pytest

from tests.generic_modifier_helpers import generic_effect
from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.attack_sequence import attack_sequence_hit_roll_spec
from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.weapon_abilities import SNAP_SHOOTING_RULE_ID


@pytest.mark.parametrize("snap", [False, True])
@pytest.mark.parametrize("raw", range(1, 7))
@pytest.mark.parametrize("modifier", [-1, 0, 1])
def test_critical_four_succeeds_below_skill_except_snap(
    section04_definitions: Section02Definitions, snap: bool, raw: int, modifier: int
) -> None:
    d = section04_definitions
    attacker = d.unit(LORD_EXULTANT)
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    state = combat_state(d, attacker, target=target)
    state.record_persisting_effect(
        generic_effect(
            effect_id="constructed:critical-four",
            owner_player_id="owner",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "attack_role": "attacker",
                "roll_type": "hit",
                "status": "critical_hit_threshold",
                "critical_threshold": 4,
            },
        )
    )
    native = d.weapon(f"{LORD_EXULTANT}:bolt-pistol")
    contract = replace(
        native,
        profile_id="constructed:skill-five",
        name="Core BS5 threshold contract",
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 5),
        source_ids=("constructed:section04:threshold",),
    )
    pool = replace(
        attack_pool(attacker, target, contract, f"{LORD_EXULTANT}:bolt-pistol"),
        targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,) if snap else (),
        hit_roll_modifier=modifier,
        hit_roll_modifiers=(
            RollModifier("constructed:modifier", modifier, source_id="constructed:section04"),
        )
        if modifier
        else (),
    )
    spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=contract.profile_id,
        attack_context_id="section04:attack",
        attacker_player_id="owner",
        reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,) if snap else (),
    )
    result = DiceRollManager("physical").roll_fixed(spec, (raw,)).original_result
    hit = _roll_hit(
        state=state,
        manager=DiceRollManager("section04", injected_results=(result,)),
        pool=pool,
        attacker_player_id="owner",
        attack_context_id="section04:attack",
        source_phase=BattlePhase.SHOOTING,
    )
    assert hit.successful is (raw == 6 if snap else raw >= 4 or (raw > 1 and raw + modifier >= 5))
    assert hit.critical is (not snap and raw >= 4)
    assert hit.unmodified_roll == raw
    assert hit.final_roll == max(1, raw + modifier)
    assert bool(hit.threshold_source_ids)
