"""Complete reserve physical groups and carrier routes on native selected bodies."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement, scenario
from tests.support.section09_fixtures import unplace
from tests.support.section18_fixtures import transport_scene
from tests.support.section19_fixtures import attached_scene
from tests.support.section20_fixtures import ingress_request, section20_session, submit_ingress
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.reserve_destruction import (
    final_turn_cleanup_policy,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.reserve_lifetime_boundary import apply_destruction, resolve_boundary
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
    ReserveStatus,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("end", [False, True])
def test_native_carrier_and_cargo_deadlines_preserve_route_and_suppress_model_reactions(
    section20_definitions: Section02Definitions, end: bool
) -> None:
    s = transport_scene(section20_definitions)
    state = s.state
    state.replace_battlefield_state(unplace(state, s.transport))
    state.battle_round = 5 if end else 3
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="owner",
            unit_instance_id=s.transport.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            embarked_unit_instance_ids=(s.passenger.unit_instance_id,),
        )
    )
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    record_primary_turn_start_evidence_for_fixture(
        state, decisions=s.session.lifecycle.decision_controller
    )
    assert state.battlefield_state is not None
    result = resolve_unarrived_reserve_destruction(
        reserve_states=tuple(state.reserve_states),
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
        policy=final_turn_cleanup_policy()
        if end
        else ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=state.battle_round,
        end_of_battle=end,
    )
    assert set(result.destroyed_unit_instance_ids) == {
        s.transport.unit_instance_id,
        s.passenger.unit_instance_id,
    }
    events = s.session.lifecycle.decision_controller.event_log.records
    apply_destruction(state, destruction=result)
    assert state.reserve_states[0].status is ReserveStatus.DESTROYED
    assert not state.transport_cargo_states
    assert all(
        not model_by_id(state=state, model_instance_id=mid).is_alive
        for u in (s.transport, s.passenger)
        for mid in u.own_model_ids()
    )
    assert not state.pending_return_on_death
    assert s.session.lifecycle.decision_controller.event_log.records == events


def test_carrier_ingress_keeps_cargo_off_board_and_protects_its_deadline(
    section20_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section20_definitions)
    s.state.replace_battlefield_state(unplace(s.state, s.transport))
    s.state.battle_round = 2
    s.state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="owner",
            unit_instance_id=s.transport.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            embarked_unit_instance_ids=(s.passenger.unit_instance_id,),
        )
    )
    session = section20_session(section20_definitions, s.state)
    request = ingress_request(session, s.transport)
    assert s.passenger.unit_instance_id not in {o.option_id for o in request.options}
    status = submit_ingress(session, request, s.transport, (Pose.at(2, 20),))
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert s.state.battlefield_state is not None
    assert s.state.battlefield_state.unit_placement_or_none(s.passenger.unit_instance_id) is None
    assert s.state.transport_cargo_states[0].embarked_unit_instance_ids == (
        s.passenger.unit_instance_id,
    )
    assert s.state.reserve_state_for_unit(s.passenger.unit_instance_id) is None
    s.state.battle_round = 3
    before = s.state.battlefield_state
    resolve_boundary(s.state, end_of_battle=False)
    assert s.state.battlefield_state == before
    assert all(
        model_by_id(state=s.state, model_instance_id=mid).is_alive
        for mid in s.passenger.own_model_ids()
    )


@pytest.mark.parametrize("complete", [False, True])
def test_native_attached_ingress_requires_every_component_and_complete_physical_inventory(
    section20_definitions: Section02Definitions, complete: bool
) -> None:
    s = attached_scene(section20_definitions)
    assert s.state.battlefield_state is not None
    from dataclasses import replace

    s.state.replace_battlefield_state(
        replace(
            s.state.battlefield_state,
            placed_armies=tuple(
                a for a in s.state.battlefield_state.placed_armies if a.player_id == "opponent"
            ),
        )
    )
    view = s.view
    reserve = ReserveState.declared_before_battle(
        player_id="owner",
        unit_instance_id=view.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
    )
    body = placement(s.body, tuple(Pose.at(1, 12 + i * 1.3) for i in range(len(s.body.own_models))))
    leader = placement(s.leader, (Pose.at(2.4, 14),))
    attempt = RulesUnitPlacement(view.unit_instance_id, (body, leader) if complete else (body,))
    result = resolve_reserve_arrival(
        scenario=scenario(s.state),
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        reserve_state=reserve,
        attempted_placement=attempt,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid is complete
    assert (result.transition_batch is not None) is complete
    if complete:
        assert result.transition_batch is not None
        assert {p.model_instance_id for p in result.transition_batch.placements} == {
            m.model_instance_id for m in view.own_models
        }
    else:
        assert "unit_placement_drift" in {v.violation_code.value for v in result.violations}
