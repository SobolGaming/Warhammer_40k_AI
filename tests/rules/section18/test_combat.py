"""18.04 mode priority, six-inch Combat placement and real hazard consumer."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section18_fixtures import (
    AVENGERS,
    YRIEL,
    contact_poses,
    elevate_carrier,
    transport_scene,
)
from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.hazard import hazard_roll_spec
from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
    RulesUnitDisembarkSelection,
    resolve_rules_unit_combat_disembark,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportMovementStatus,
    resolve_disembark_internal,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("elevated", [False, True])
@pytest.mark.parametrize("sheet", [YRIEL, AVENGERS])
def test_combat_requires_proved_tactical_impossibility_and_rolls_only_after_valid_setup(
    section18_definitions: Section02Definitions,
    elevated: bool,
    sheet: str,
) -> None:
    s = transport_scene(section18_definitions, passenger_sheet=sheet)
    if elevated:
        elevate_carrier(s)
    attempted = s.selection(poses=contact_poses(s)).attempted_placement
    selection = RulesUnitDisembarkSelection(
        "owner",
        1,
        s.passenger.unit_instance_id,
        s.transport.unit_instance_id,
        RulesUnitPlacement(s.passenger.unit_instance_id, (attempted,)),
        DisembarkModeKind.COMBAT_DISEMBARK,
        TransportMovementStatus.NOT_MOVED,
    )
    dice = DiceRollManager(
        18,
        injected_results=tuple(
            DiceRollResult.from_values(
                roll_id=f"s18:combat-hazard:{i}",
                spec=hazard_roll_spec(
                    reason=f"Combat Disembark hazard roll for {model.model_instance_id}",
                    roll_type="combat_disembark.hazard_roll",
                    actor_id=model.model_instance_id,
                ),
                values=(6,),
                source="injected",
            )
            for i, model in enumerate(s.passenger.own_models)
        ),
    )
    result = resolve_rules_unit_combat_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=selection,
        rules_unit=rules_unit_view_from_armies(
            armies=s.scenario.armies, unit_instance_id=s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        dice_manager=dice,
    )
    assert result.placement.is_valid is elevated, result.placement.violations
    if elevated:
        assert len(result.model_rolls) == len(s.passenger.own_models)
        assert all(r.roll.roll_state.current_total == 6 for r in result.model_rolls)
        assert result.placement.disembarked_unit_state is not None
        assert result.placement.disembarked_unit_state.battle_shocked_until == "until_cleared"
        assert not result.placement.disembarked_unit_state.can_declare_charge
        assert not result.placement.disembarked_unit_state.can_move_further
        assert not result.tactical_resolution.is_valid
    else:
        assert {v.violation_code.value for v in result.placement.violations} == {
            "combat_disembark_tactical_available"
        }
        assert result.tactical_resolution.is_valid
        assert not result.model_rolls
        assert not dice.event_log.records


@pytest.mark.parametrize(("enemy_x", "allowed"), [(23.9, True), (25, False)])
def test_combat_endpoint_can_engage_only_enemies_already_engaged_with_its_transport(
    section18_definitions: Section02Definitions,
    enemy_x: float,
    allowed: bool,
) -> None:
    s = transport_scene(section18_definitions, enemy_poses=(Pose.at(enemy_x, 20),))
    # This is the shared endpoint boundary, deliberately independent of the
    # separately tested complete Tactical-impossibility admission service.
    result = resolve_disembark_internal(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=s.cargo,
        selection=s.selection(DisembarkModeKind.COMBAT_DISEMBARK, poses=(Pose.at(22.1, 20),)),
        unit=s.passenger,
        transport_placement=s.carrier_placement,
        turn_player_id="owner",
        require_started_phase_embarked=True,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        terrain_features=(),
        objective_markers=(),
    )
    assert result.is_valid is allowed, result.violations
    assert {v.violation_code.value for v in result.violations} == (
        set() if allowed else {"enemy_engagement_range"}
    )
