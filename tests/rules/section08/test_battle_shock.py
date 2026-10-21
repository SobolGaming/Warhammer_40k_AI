"""Native rule eligibility and one-roll suppression, without earlier phases."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section08_fixtures import command_state, damage_to_count, mark_shocked, requests
from warhammer40k_core.engine.battle_shock import BattleShockTestReason
from warhammer40k_core.engine.command_battle_shock_candidates import (
    command_battle_shock_candidate_inventory,
)
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model


@pytest.mark.parametrize(
    ("sheet", "remaining", "required"),
    [
        ("000004080", 6, False),
        ("000004080", 5, True),
        ("000004080", 4, True),
        ("000000592", 3, False),
        ("000000592", 2, True),
        ("000000592", 1, True),
    ],
)
@pytest.mark.parametrize("shocked", [False, True])
def test_native_model_strength_and_existing_shock_are_independent_eligibility_reasons(
    section08_definitions: Section02Definitions,
    sheet: str,
    remaining: int,
    required: bool,
    shocked: bool,
) -> None:
    state = command_state(section08_definitions, sheet)
    damage_to_count(state, remaining)
    if shocked:
        mark_shocked(state)
    before = state.to_payload()
    actual = requests(state)
    assert len(actual) == int(required or shocked)
    inventory = command_battle_shock_candidate_inventory(state, "owner", ())
    assert len(inventory) == 1
    assert inventory[0].is_battle_shocked is shocked
    assert inventory[0].below_half_strength_context.is_at_or_below_half_strength is required
    if actual:
        assert actual[0].reason is BattleShockTestReason.COMMAND_PHASE_REQUIRED
        assert (
            actual[0].unit_instance_id
            == next(a for a in state.army_definitions if a.player_id == "owner")
            .units[0]
            .unit_instance_id
        )
    assert state.to_payload() == before


@pytest.mark.parametrize(("offset", "required"), [(1, False), (0, True), (-1, True)])
def test_native_single_vehicle_uses_wounds_at_the_inclusive_half_boundary(
    section08_definitions: Section02Definitions, offset: int, required: bool
) -> None:
    state = command_state(section08_definitions, "000000968")
    unit = next(a for a in state.army_definitions if a.player_id == "owner").units[0]
    model = unit.own_models[0]
    assert len(unit.own_models) == 1
    assert model.current_wounds % 2 == 0
    wounds = model.current_wounds // 2 + offset
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.current_wounds - wounds,
        damage_kind=DamageKind.NORMAL,
    )
    actual = requests(state)
    assert len(actual) == int(required)
    if actual:
        assert actual[0].below_half_strength_context.single_model_wounds_remaining == wounds


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("remaining", [4, 5, 6, 10])
def test_forced_test_suppresses_core_roll_unless_explicitly_overridden(
    section08_definitions: Section02Definitions, remaining: int, duplicate: bool
) -> None:
    state = command_state(section08_definitions)
    damage_to_count(state, remaining)
    mark_shocked(state)
    actual = requests(state, forced=True, duplicate=duplicate)
    expected = [BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED] if remaining < 10 else []
    if remaining == 10 or duplicate:
        expected.append(BattleShockTestReason.COMMAND_PHASE_REQUIRED)
    assert sorted(r.reason for r in actual) == sorted(expected)
    assert len({r.request_id for r in actual}) == len(actual)


def test_only_active_living_units_enter_step_inventory(
    section08_definitions: Section02Definitions,
) -> None:
    state = command_state(section08_definitions)
    damage_to_count(state, 0)
    state.active_player_id = "opponent"
    mark_shocked(state)
    state.active_player_id = "owner"
    assert requests(state) == ()
    assert command_battle_shock_candidate_inventory(state, "owner", ()) == ()
    state.active_player_id = "opponent"
    assert len(requests(state)) == 1
