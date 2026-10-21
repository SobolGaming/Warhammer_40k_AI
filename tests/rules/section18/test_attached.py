"""Physical whole-unit predicates across an explicit attached Core group.

Attachment/cargo are constructed supported-input contracts on native definitions;
no Yriel-to-Avenger attachment provider or mixed roster admission is claimed.
"""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement
from tests.support.section09_fixtures import add_unit, unplace
from tests.support.section18_fixtures import AVENGERS, YRIEL, transport_scene
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
    RulesUnitDisembarkSelection,
    resolve_rules_unit_disembark,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    EmbarkSelection,
    TransportMovementStatus,
    resolve_embark,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("capacity", "leader_far", "valid"), [(6, False, True), (5, False, False), (6, True, False)]
)
@pytest.mark.parametrize("selected_leader", [False, True])
def test_attached_embark_capacity_and_distance_include_every_living_component(
    section18_definitions: Section02Definitions,
    capacity: int,
    leader_far: bool,
    valid: bool,
    selected_leader: bool,
) -> None:
    s = transport_scene(
        section18_definitions,
        embarked=False,
        passenger_sheet=AVENGERS,
        capacity=capacity,
        passenger_poses=(
            Pose.at(22, 18),
            Pose.at(23.2, 18.5),
            Pose.at(23.5, 20),
            Pose.at(23.2, 21.5),
            Pose.at(22, 22),
        ),
    )
    leader = section18_definitions.unit(YRIEL, identity="attached-leader")
    add_unit(s.state, leader, (Pose.at(30 if leader_far else 20, 23),))
    attached_id = "attached-unit:section02:s18"
    components = tuple(sorted((s.passenger.unit_instance_id, leader.unit_instance_id)))
    s.state.army_definitions[:] = [
        replace(
            a,
            attached_units=(
                AttachedUnitFormation(
                    attached_unit_instance_id=attached_id,
                    bodyguard_unit_instance_id=s.passenger.unit_instance_id,
                    leader_unit_instance_ids=(leader.unit_instance_id,),
                    component_unit_instance_ids=components,
                    source_id="constructed:s18:attachment",
                    attachment_source_ids=("constructed:s18:attachment-permission",),
                ),
            ),
        )
        if a.player_id == "owner"
        else a
        for a in s.state.army_definitions
    ]
    selected = leader if selected_leader else s.passenger
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "owner",
            1,
            selected.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(selected.unit_instance_id),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="owner",
    )
    assert result.is_valid is valid, result.violations
    if valid:
        assert result.updated_cargo_state is not None
        assert result.updated_cargo_state.embarked_unit_instance_ids == components
        assert result.transition_batch is not None
        assert {r.model_instance_id for r in result.transition_batch.removals} == {
            *s.passenger.own_model_ids(),
            *leader.own_model_ids(),
        }
    else:
        assert result.updated_cargo_state is None
        assert result.transition_batch is None
        assert {v.violation_code.value for v in result.violations} == {
            "embark_distance" if leader_far else "capacity_exceeded"
        }


@pytest.mark.parametrize("omit_component", [False, True])
def test_attached_disembark_cannot_leave_a_component_in_cargo(
    section18_definitions: Section02Definitions,
    omit_component: bool,
) -> None:
    s = transport_scene(section18_definitions, passenger_sheet=AVENGERS)
    leader = section18_definitions.unit(YRIEL, identity="attached-leader")
    add_unit(s.state, leader, (Pose.at(30, 20),))
    s.state.replace_battlefield_state(unplace(s.state, leader))
    attached_id = "attached-unit:section02:s18"
    components = tuple(sorted((s.passenger.unit_instance_id, leader.unit_instance_id)))
    s.state.army_definitions[:] = [
        replace(
            a,
            attached_units=(
                AttachedUnitFormation(
                    attached_unit_instance_id=attached_id,
                    bodyguard_unit_instance_id=s.passenger.unit_instance_id,
                    leader_unit_instance_ids=(leader.unit_instance_id,),
                    component_unit_instance_ids=components,
                    source_id="constructed:s18:attachment",
                    attachment_source_ids=("constructed:s18:attachment-permission",),
                ),
            ),
        )
        if a.player_id == "owner"
        else a
        for a in s.state.army_definitions
    ]
    cargo = replace(s.cargo, embarked_unit_instance_ids=components)
    squad_place = placement(
        s.passenger,
        (
            Pose.at(22, 18),
            Pose.at(23.2, 18.5),
            Pose.at(23.5, 20),
            Pose.at(23.2, 21.5),
            Pose.at(22, 22),
        ),
    )
    leader_place = placement(leader, (Pose.at(20.5, 22.8),))
    group = RulesUnitPlacement(
        attached_id, (squad_place,) if omit_component else (squad_place, leader_place)
    )
    if omit_component:
        before = s.state.to_payload()
        with pytest.raises(GameLifecycleError, match="component identity drift"):
            resolve_rules_unit_disembark(
                scenario=s.scenario,
                ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
                cargo_state=cargo,
                selection=RulesUnitDisembarkSelection(
                    "owner",
                    1,
                    attached_id,
                    s.transport.unit_instance_id,
                    group,
                    DisembarkModeKind.TACTICAL_DISEMBARK,
                    TransportMovementStatus.NOT_MOVED,
                ),
                rules_unit=rules_unit_view_from_armies(
                    armies=s.scenario.armies, unit_instance_id=attached_id
                ),
                transport_placement=s.carrier_placement,
                turn_player_id="owner",
            )
        assert s.state.to_payload() == before
        return
    result = resolve_rules_unit_disembark(
        scenario=s.scenario,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        cargo_state=cargo,
        selection=RulesUnitDisembarkSelection(
            "owner",
            1,
            attached_id,
            s.transport.unit_instance_id,
            group,
            DisembarkModeKind.TACTICAL_DISEMBARK,
            TransportMovementStatus.NOT_MOVED,
        ),
        rules_unit=rules_unit_view_from_armies(
            armies=s.scenario.armies, unit_instance_id=attached_id
        ),
        transport_placement=s.carrier_placement,
        turn_player_id="owner",
    )
    assert result.is_valid, result.violations
    assert result.updated_cargo_state is not None
    assert not result.updated_cargo_state.embarked_unit_instance_ids
    assert result.transition_batch is not None
    assert len(result.transition_batch.placements) == 6
