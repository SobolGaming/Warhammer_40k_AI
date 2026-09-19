"""Real transport fixtures for same-turn setup and embark tests."""

from __future__ import annotations

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.disembark_eligibility_helpers import TRANSPORT_ID, disembark_session
from tests.order60_emergency_disembark_helpers import emergency_disembark_poses_around
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement_fall_back_embark import (
    _post_move_embark_options,
)
from warhammer40k_core.engine.transports import TransportMovementStatus

UNIT_ID = "army-alpha:remaining-unit"


def embark_session() -> LocalGameSession:
    session = disembark_session()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    placement = scenario.battlefield_state.unit_placement_by_id(UNIT_ID)
    _replace_unit_poses(
        state,
        unit_instance_id=UNIT_ID,
        poses=emergency_disembark_poses_around(
            center_x=10, center_y=10, count=len(placement.model_placements), step_degrees=40
        ),
    )
    return session


def embark_option_ids(session: LocalGameSession) -> tuple[str, ...]:
    state = session.lifecycle.state
    if state is None:
        raise GameLifecycleError("Embark test needs initialized state.")
    return tuple(
        option.option_id
        for option in _post_move_embark_options(
            state=state,
            unit_instance_id=UNIT_ID,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        )
    )


__all__ = ("TRANSPORT_ID", "UNIT_ID", "embark_option_ids", "embark_session")
