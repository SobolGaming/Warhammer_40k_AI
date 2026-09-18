from __future__ import annotations

import json

from tests.disembark_eligibility_helpers import PASSENGER_ID
from tests.order60_emergency_disembark_helpers import (
    order60_emergency_session,
    order60_omit_unplaceable_large_placement,
    order60_passenger_placement,
    order60_place_enemies_near_transport,
    order60_resolve_emergency,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.transports import TransportOperationViolationCode
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_emergency_disembark_placement_2026_09 as placement_source,
)


def test_emergency_disembark_places_every_survivor_on_the_closest_ring() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid, result.violations
    assert result.updated_cargo_state is not None
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.battle_shocked_until == "end_of_turn"
    assert type(result).from_payload(result.to_payload()) == result
    assert placement_source.PLACEMENT_POLICY.destroys_only_unplaceable_models is True


def test_emergency_disembark_rejects_omitting_a_placeable_survivor() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(
        session,
        order60_passenger_placement(session, omit_last=True),
    )
    assert result.is_valid is False
    assert any(
        violation.violation_code
        is TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
        and violation.source_rule_id == placement_source.EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID
        for violation in result.violations
    )
    assert result.updated_cargo_state is None


def test_emergency_disembark_rejects_a_pose_that_is_not_closest() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session, far=True))
    assert result.is_valid is False
    assert any(
        violation.violation_code is TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST
        and violation.source_rule_id == placement_source.EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID
        for violation in result.violations
    )


def test_emergency_disembark_rejects_engaged_when_unengaged_exists() -> None:
    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    order60_place_enemies_near_transport(state)
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid is False
    assert any(
        violation.violation_code is TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE
        for violation in result.violations
    )


def test_emergency_disembark_destroys_only_a_genuinely_unplaceable_model() -> None:
    session = order60_emergency_session(oversized_base_diameter_inches=45)
    result = order60_resolve_emergency(session, order60_omit_unplaceable_large_placement(session))
    state = session.lifecycle.state
    assert state is not None
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    large_id = passenger.own_models[0].model_instance_id
    assert result.is_valid, result.violations
    assert all(
        violation.violation_code
        is not TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
        for violation in result.violations
    )
    omitted = {model.model_instance_id for model in passenger.own_models} - {
        placement.model_instance_id
        for placement in result.selection.attempted_placement.model_placements
    }
    assert omitted == {large_id}


def test_emergency_disembark_restore_preserves_valid_resolution() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid
    restored_lifecycle = GameLifecycle.from_payload(
        json.loads(json.dumps(session.lifecycle.to_payload()))
    )
    restored = LocalGameSession(lifecycle=restored_lifecycle)
    restored_result = order60_resolve_emergency(
        restored,
        order60_passenger_placement(restored),
    )
    assert restored_result.to_payload() == result.to_payload()
    for viewer in ("player-a", "player-b"):
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
