"""SF21-R002: shared reactive witness inventory rejects before commit."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section21_fixtures import offer_surge, submit_surge, surge_path, surge_scene
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.triggered_movement import TriggeredMovementKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("kind", [TriggeredMovementKind.SURGE, TriggeredMovementKind.TRIGGERED])
@pytest.mark.parametrize("mismatch", ["missing", "extra", "foreign"])
def test_public_reactive_witness_wrong_inventory_is_atomic_and_retriable(
    section21_definitions: Section02Definitions, kind: TriggeredMovementKind, mismatch: str
) -> None:
    s = surge_scene(section21_definitions, multi=True, gap=9)
    session = s.session()
    request = offer_surge(session, s, kind=kind)
    option = (
        f"surge:{s.unit.unit_instance_id}:target:{s.target.unit_instance_id}"
        if kind is TriggeredMovementKind.SURGE
        else f"triggered:{s.unit.unit_instance_id}"
    )
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:inventory-select", option_id=option
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    full = surge_path(s, (4, 4))
    rows = list(full.model_paths)
    if mismatch == "missing":
        rows = rows[:1]
    elif mismatch == "extra":
        rows.append((s.target.own_model_ids()[0], (Pose.at(20, 10), Pose.at(24, 10))))
    else:
        rows[0] = (s.target.own_model_ids()[0], rows[0][1])
    before = s.state.to_payload()
    decisions = session.lifecycle.decision_controller.to_payload()
    invalid = submit_surge(
        session, request, PathWitness.for_paths(tuple(rows)), result_id="s21:wrong-inventory"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "movement_witness_model_inventory_mismatch" in str(invalid.to_payload())
    assert s.state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == decisions
    assert session.lifecycle.pending_decision_request() == request
    status = submit_surge(session, request, full, result_id="s21:inventory-retry")
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert len(s.state.phase_movement_history) == 1
    assert s.state.phase_movement_history[0].is_surge is (kind is TriggeredMovementKind.SURGE)
