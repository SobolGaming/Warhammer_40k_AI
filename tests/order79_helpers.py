"""Canonical boundary scenes shared by Order 79 regressions and measurements."""

from tests.aircraft_helpers import aircraft_session
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.geometry.pose import Pose


def control_session(*, turn_owner: str = "player-b", on_objective: bool = True) -> LocalGameSession:
    session = aircraft_session(turn_owner=turn_owner)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    if on_objective:
        marker = state.mission_setup.objective_markers[0]
        battlefield = state.battlefield_state
        unit = battlefield.unit_placement_by_id("army-alpha:aircraft")
        # Canonical fixture placement precedes the persisted/replay root, not a live move.
        state.battlefield_state = battlefield.with_unit_placement(
            unit.with_model_placements(
                tuple(
                    model.with_pose(Pose.at(marker.x_inches, marker.y_inches))
                    for model in unit.model_placements
                )
            )
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
