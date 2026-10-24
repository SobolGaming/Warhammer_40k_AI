"""18.03/18.05: hazard-before-placement, closest setup and omission proofs."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import add_enemy
from tests.support.section18_fixtures import (
    AVENGERS,
    contact_poses,
    replace_passenger,
    transport_scene,
)
from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.hazard import hazard_roll_spec
from warhammer40k_core.engine.transports import (
    DestroyedTransportDisembark,
    DisembarkModeKind,
    apply_destroyed_transport_disembark_to_battlefield,
    resolve_destroyed_transport_disembark,
    resolve_destroyed_transport_hazard_rolls,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("values", [(6, 6, 6, 6, 6), (1, 2, 3, 4, 5)])
def test_emergency_rolls_for_every_native_passenger_before_any_setup_and_retains_exact_rolls(
    section18_definitions: Section02Definitions,
    values: tuple[int, ...],
) -> None:
    s = transport_scene(section18_definitions, passenger_sheet=AVENGERS)
    dice = DiceRollManager(
        18,
        injected_results=tuple(
            DiceRollResult.from_values(
                roll_id=f"s18-hazard-{i}",
                spec=hazard_roll_spec(
                    reason=f"Emergency Disembark hazard roll for {model.model_instance_id}",
                    roll_type="destroyed_transport_disembark",
                    actor_id=model.model_instance_id,
                ),
                values=(value,),
                source="injected",
            )
            for i, (model, value) in enumerate(zip(s.passenger.own_models, values, strict=True))
        ),
    )
    before = s.state.to_payload()
    rolls = resolve_destroyed_transport_hazard_rolls(
        cargo_state=s.cargo, unit=s.passenger, dice_manager=dice, battle_round=1
    )
    assert len(rolls.model_rolls) == len(s.passenger.own_models) == 5
    assert rolls.model_instance_ids == s.passenger.own_model_ids()
    assert rolls.mortal_wound_count == sum(value <= 2 for value in values)
    assert [r.roll_state.current_total for r in rolls.model_rolls] == list(values)
    assert rolls.mortal_wounds_per_failed_roll == 1
    assert s.state.to_payload() == before
    assert type(rolls).from_payload(rolls.to_payload()) == rolls
    assert len(dice.event_log.records) == 5


@pytest.mark.parametrize(
    ("extra", "valid", "code"),
    [
        (0.02, True, None),
        (0.5, False, "emergency_disembark_not_closest"),
        (5, False, "disembark_distance"),
    ],
)
def test_emergency_requires_closest_legal_setup_within_six_before_carrier_removal(
    section18_definitions: Section02Definitions,
    extra: float,
    valid: bool,
    code: str | None,
) -> None:
    s = transport_scene(section18_definitions)
    rp = s.passenger.own_models[0].geometry.parts[0].radius_x_inches
    rt = s.transport.own_models[0].geometry.parts[0].radius_x_inches
    dice = DiceRollManager(18)
    rolls = resolve_destroyed_transport_hazard_rolls(
        cargo_state=s.cargo, unit=s.passenger, dice_manager=dice, battle_round=1
    )
    result = resolve_destroyed_transport_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=s.selection(
            DisembarkModeKind.EMERGENCY_DISEMBARK, poses=(Pose.at(20 + rp + rt + extra, 20),)
        ),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
        hazard_rolls=rolls,
        turn_player_id="opponent",
    )
    assert result.placement.is_valid is valid, result.placement.violations
    assert (
        s.scenario.battlefield_state.unit_placement_or_none(s.transport.unit_instance_id)
        is not None
    )
    assert len(result.model_rolls) == 1
    if valid:
        assert not result.destroyed_model_instance_ids
        after = apply_destroyed_transport_disembark_to_battlefield(
            battlefield_state=s.scenario.battlefield_state, disembark=result
        )
        assert after.unit_placement_or_none(s.passenger.unit_instance_id) is not None
        assert after.unit_placement_or_none(s.transport.unit_instance_id) is not None
        outcome = result.disembarked_unit_state
        assert outcome is not None
        assert outcome.turn_player_id == "opponent"
        assert outcome.battle_shocked_until == "until_cleared"
        assert not outcome.can_declare_charge
        assert DestroyedTransportDisembark.from_payload(result.to_payload()) == result
    else:
        assert code in {v.violation_code.value for v in result.placement.violations}
        assert result.placement.updated_cargo_state is None
        assert result.placement.transition_batch is None


def test_emergency_prefers_an_unengaged_legal_point_over_engaged_contact(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, enemy_poses=(Pose.at(24, 20),))
    rp = s.passenger.own_models[0].geometry.parts[0].radius_x_inches
    rt = s.transport.own_models[0].geometry.parts[0].radius_x_inches
    rolls = resolve_destroyed_transport_hazard_rolls(
        cargo_state=s.cargo, unit=s.passenger, dice_manager=DiceRollManager(18), battle_round=1
    )
    for direction, valid in ((1, False), (-1, True)):
        result = resolve_destroyed_transport_disembark(
            scenario=s.scenario,
            ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
            cargo_state=s.cargo,
            selection=s.selection(
                DisembarkModeKind.EMERGENCY_DISEMBARK,
                poses=(Pose.at(20 + direction * (rp + rt + 0.02), 20),),
            ),
            unit=s.passenger,
            transport_placement=s.carrier_placement,
            hazard_rolls=rolls,
            turn_player_id="owner",
        )
        assert result.placement.is_valid is valid, result.placement.violations
        if not valid:
            assert "enemy_engagement_range" in {
                v.violation_code.value for v in result.placement.violations
            }


def test_emergency_cannot_omit_a_placeable_model(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, passenger_sheet=AVENGERS)
    selection = s.selection(DisembarkModeKind.EMERGENCY_DISEMBARK, poses=contact_poses(s))
    selection = replace(
        selection,
        attempted_placement=replace(
            selection.attempted_placement,
            model_placements=selection.attempted_placement.model_placements[:-1],
        ),
    )
    rolls = resolve_destroyed_transport_hazard_rolls(
        cargo_state=s.cargo, unit=s.passenger, dice_manager=DiceRollManager(18), battle_round=1
    )
    result = resolve_destroyed_transport_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=selection,
        unit=s.passenger,
        transport_placement=s.carrier_placement,
        hazard_rolls=rolls,
        turn_player_id="owner",
    )
    assert not result.placement.is_valid
    assert "emergency_disembark_omitted_model_placeable" in {
        v.violation_code.value for v in result.placement.violations
    }
    assert result.placement.updated_cargo_state is None
    assert result.placement.transition_batch is None


def test_emergency_permits_engaged_closest_setup_when_no_unengaged_point_exists(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, enemy_poses=(Pose.at(24.5, 20),))
    for i in range(1, 12):
        angle = radians(i * 30)
        add_enemy(
            section18_definitions,
            s.state,
            identity=f"ring-{i}",
            x=20 + 4.5 * cos(angle),
            y=20 + 4.5 * sin(angle),
        )
    rolls = resolve_destroyed_transport_hazard_rolls(
        cargo_state=s.cargo, unit=s.passenger, dice_manager=DiceRollManager(18), battle_round=1
    )
    result = resolve_destroyed_transport_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=s.selection(DisembarkModeKind.EMERGENCY_DISEMBARK, poses=contact_poses(s)),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
        hazard_rolls=rolls,
        turn_player_id="owner",
    )
    assert result.placement.is_valid, result.placement.violations
    assert not result.destroyed_model_instance_ids
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.battle_shocked_until == "until_cleared"


def test_emergency_destroys_only_a_proved_unplaceable_model_and_sets_up_the_rest(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, passenger_sheet=AVENGERS)
    # Explicit analytical geometry contract: the first survivor has a 50-inch
    # circular support footprint, which cannot fit on the 44-inch-deep board.
    first = s.passenger.own_models[0]
    giant = replace(
        first,
        geometry=replace(
            first.geometry,
            parts=(replace(first.geometry.parts[0], radius_x_inches=25, radius_y_inches=25),),
        ),
    )
    poses = contact_poses(s)
    replace_passenger(s, replace(s.passenger, own_models=(giant, *s.passenger.own_models[1:])))
    selection = s.selection(DisembarkModeKind.EMERGENCY_DISEMBARK, poses=poses)
    selection = replace(
        selection,
        attempted_placement=replace(
            selection.attempted_placement,
            model_placements=selection.attempted_placement.model_placements[1:],
        ),
    )
    rolls = resolve_destroyed_transport_hazard_rolls(
        cargo_state=s.cargo, unit=s.passenger, dice_manager=DiceRollManager(18), battle_round=1
    )
    result = resolve_destroyed_transport_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=selection,
        unit=s.passenger,
        transport_placement=s.carrier_placement,
        hazard_rolls=rolls,
        turn_player_id="owner",
    )
    assert result.placement.is_valid, result.placement.violations
    assert result.destroyed_model_instance_ids == (first.model_instance_id,)
    assert not result.hazard_destroyed_model_instance_ids
    assert result.placement.transition_batch is not None
    assert {p.model_instance_id for p in result.placement.transition_batch.placements} == set(
        s.passenger.own_model_ids()[1:]
    )
