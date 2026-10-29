"""02.04 direct weapon consumers, with real source profiles and opponents."""

import pytest

from tests.support.section02_fixtures import AVENGERS, INFRACTORS, MAULERFIEND, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attack_sequence_state import wound_roll_target_number
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.saves import (
    SaveKind,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
)


def test_02_02_01_reroll_replaces_the_unmodified_result_before_ap(
    section02_definitions: Section02Definitions,
) -> None:
    target = section02_definitions.unit().own_models[0]
    weapon = section02_definitions.weapon(f"{AVENGERS}:avenger-shuriken-catapult")
    options = save_options_for_model(model=target, armor_penetration=weapon.armor_penetration.final)
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="owner",
        allocated_model_id=target.model_instance_id,
        attack_context_id="section02-reroll",
    )
    manager = DiceRollManager("section02-reroll")
    original = manager.roll_fixed(spec, (2,))
    replacement = manager.roll_fixed(spec, (4,))
    rerolled = original.with_reroll(
        decision_id="reroll",
        request_id="request",
        selected_indices=(0,),
        replacement_result=replacement.original_result,
    )
    result = resolve_saving_throw(roll_state=rerolled, options=options)
    assert result.unmodified_roll == 4
    assert result.final_roll == 3
    assert result.successful
    assert original.current_total == 2


@pytest.mark.parametrize(
    ("weapon_id", "target_id", "threshold"),
    [
        (f"{AVENGERS}:avenger-shuriken-catapult", AVENGERS, 3),
        (f"{AVENGERS}:avenger-shuriken-catapult", INFRACTORS, 4),
        (f"{AVENGERS}:avenger-shuriken-catapult", MAULERFIEND, 6),
        (f"{MAULERFIEND}:maulerfiend-fists", INFRACTORS, 2),
        (f"{MAULERFIEND}:maulerfiend-fists", MAULERFIEND, 3),
    ],
)
def test_02_04_strength_compares_real_weapon_and_target_profiles(
    section02_definitions: Section02Definitions,
    weapon_id: str,
    target_id: str,
    threshold: int,
) -> None:
    weapon = section02_definitions.weapon(weapon_id)
    target = section02_definitions.unit(target_id).own_models[0]
    assert (
        wound_roll_target_number(
            strength=weapon.strength_for_interaction(),
            toughness=target.characteristic(Characteristic.TOUGHNESS).final,
        )
        == threshold
    )


@pytest.mark.parametrize(("roll", "success"), [(3, False), (4, True), (5, True)])
def test_02_04_ap_changes_the_real_armour_save_result(
    section02_definitions: Section02Definitions,
    roll: int,
    success: bool,
) -> None:
    weapon = section02_definitions.weapon(f"{AVENGERS}:avenger-shuriken-catapult")
    target = section02_definitions.unit().own_models[0]
    assert weapon.armor_penetration.final == -1
    options = save_options_for_model(model=target, armor_penetration=weapon.armor_penetration.final)
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="owner",
        allocated_model_id=target.model_instance_id,
        attack_context_id="section02-ap",
    )
    roll_state = DiceRollManager("section02-ap").roll_fixed(spec, (roll,))
    assert resolve_saving_throw(roll_state=roll_state, options=options).successful is success
