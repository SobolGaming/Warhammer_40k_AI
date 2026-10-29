"""02.02 profiles: actual save and Leadership consumers; no lifecycle setup."""

import pytest

from tests.support.section02_fixtures import AVENGERS, INFRACTORS, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.saves import (
    SaveKind,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord


@pytest.mark.parametrize(
    ("datasheet", "armor", "invulnerable"),
    [
        (INFRACTORS, 3, None),
        (AVENGERS, 4, 5),
    ],
)
def test_02_02_save_profiles_produce_real_save_options(
    section02_definitions: Section02Definitions,
    datasheet: str,
    armor: int,
    invulnerable: int | None,
) -> None:
    model = section02_definitions.unit(datasheet).own_models[0]
    options = save_options_for_model(model=model, armor_penetration=0)
    assert {o.save_kind: o.characteristic_target_number for o in options} == (
        {SaveKind.ARMOUR: armor}
        if invulnerable is None
        else {SaveKind.ARMOUR: armor, SaveKind.INVULNERABLE: invulnerable}
    )


@pytest.mark.parametrize(("roll", "successful"), [(2, False), (3, True), (4, True)])
def test_02_02_armor_threshold_is_inclusive(
    section02_definitions: Section02Definitions,
    roll: int,
    successful: bool,
) -> None:
    model = section02_definitions.unit().own_models[0]
    options = save_options_for_model(model=model, armor_penetration=0)
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="owner",
        allocated_model_id=model.model_instance_id,
        attack_context_id="section02-save",
    )
    result = resolve_saving_throw(
        roll_state=DiceRollManager("section02-save").roll_fixed(spec, (roll,)), options=options
    )
    assert result.successful is successful


@pytest.mark.parametrize(("values", "passed"), [((2, 3), False), ((3, 3), True), ((3, 4), True)])
def test_02_02_leadership_threshold_consumes_real_profile(
    section02_definitions: Section02Definitions,
    values: tuple[int, int],
    passed: bool,
) -> None:
    unit = section02_definitions.unit()
    leadership = unit.own_models[0].characteristic(Characteristic.LEADERSHIP).final
    request = BattleShockTestRequest.for_unit(
        request_id="section02-leadership",
        game_id="section02",
        battle_round=1,
        player_id="owner",
        unit_instance_id=unit.unit_instance_id,
        reason=BattleShockTestReason.COMMAND_PHASE_REQUIRED,
        leadership_target=leadership,
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id="owner",
            unit=unit,
            starting_strength=StartingStrengthRecord.from_unit(player_id="owner", unit=unit),
            current_model_ids=unit.own_model_ids(),
        ),
    )
    roll = DiceRollManager("section02").roll_fixed(request.spec, values)
    assert (
        BattleShockResult.from_roll_state(
            result_id="result", request=request, roll_state=roll
        ).passed
        is passed
    )


@pytest.mark.parametrize(("roll", "successful"), [(1, False), (4, False), (5, True), (6, True)])
def test_02_02_invulnerable_threshold_is_used_when_armour_is_worse(
    section02_definitions: Section02Definitions, roll: int, successful: bool
) -> None:
    model = section02_definitions.unit(AVENGERS).own_models[0]
    options = save_options_for_model(model=model, armor_penetration=-3)
    assert {o.save_kind: o.characteristic_target_number for o in options}[
        SaveKind.INVULNERABLE
    ] == 5
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.INVULNERABLE,
        player_id="owner",
        allocated_model_id=model.model_instance_id,
        attack_context_id="invulnerable-boundary",
    )
    result = resolve_saving_throw(
        roll_state=DiceRollManager("invulnerable-boundary").roll_fixed(spec, (roll,)),
        options=options,
    )
    assert result.successful is successful
