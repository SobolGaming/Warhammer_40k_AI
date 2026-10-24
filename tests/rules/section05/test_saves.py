"""Every save face, native armour/InSv and clearly labelled impossible-armour contracts."""

import pytest

from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveResolutionRule,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
)


@pytest.mark.parametrize("datasheet", [INFRACTORS, LORD_EXULTANT])
@pytest.mark.parametrize("ap", [0, -1, -4, -10])
@pytest.mark.parametrize("raw", range(1, 7))
def test_native_save_faces_ap_and_invulnerable_priority(
    section05_definitions: Section02Definitions, datasheet: str, ap: int, raw: int
) -> None:
    model = section05_definitions.unit(datasheet).own_models[0]
    options = save_options_for_model(model=model, armor_penetration=ap)
    inv = next(
        (
            v.final
            for v in model.characteristics
            if v.characteristic is Characteristic.INVULNERABLE_SAVE and v.final > 0
        ),
        None,
    )
    armour = model.characteristic(Characteristic.SAVE).final
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.INVULNERABLE if inv else SaveKind.ARMOUR,
        player_id="opponent",
        allocated_model_id=model.model_instance_id,
        attack_context_id="s05:save",
    )
    assert (spec.expression.quantity, spec.expression.sides, spec.actor_id) == (
        1,
        6,
        "opponent",
    )
    roll = DiceRollManager("physical").roll_fixed(spec, (raw,))
    save = resolve_saving_throw(roll_state=roll, options=options)
    expected = raw != 1 and ((inv is not None and raw >= inv) or raw + ap >= armour)
    assert save.successful is expected
    if raw != 1 and inv is not None and raw >= inv:
        assert save.resolution_rule is SaveResolutionRule.INVULNERABLE_SAVE
    elif raw != 1 and raw + ap >= armour:
        assert save.resolution_rule is SaveResolutionRule.ARMOUR_SAVE
    assert save.unmodified_roll == raw
    assert resolve_saving_throw(roll_state=roll, options=tuple(reversed(options))) == save
