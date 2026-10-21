"""03.02.01 at the recorded invalid-placement boundary, without replay."""

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import native_state
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.movement_setup_failure import restore_failed_setup_selection
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.phases.movement_model import MovementUnitSelection
from warhammer40k_core.engine.phases.movement_state import MovementPhaseState


def test_failed_setup_restores_selection_and_retry_or_stationary_options(
    section03_definitions: Section02Definitions,
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    state = native_state(section03_definitions, unit)
    selection = MovementUnitSelection("owner", 1, unit.unit_instance_id, "selection", "selected")
    state.movement_phase_state = MovementPhaseState(1, "owner").with_unit_selection(selection)
    decisions = DecisionController()
    # Typed boundary contract: placement geometry/atomic rollback are tested separately.
    decisions.event_log.append(
        "disembark_placement_invalid", {"unit_instance_id": unit.unit_instance_id}
    )
    result = DecisionResult(
        "failed", "placement", "submit_disembark_placement", "owner", "submit", {}
    )
    restore_failed_setup_selection(state=state, decisions=decisions, result=result)
    assert state.movement_phase_state.selected_unit_ids == ()
    assert state.movement_phase_state.active_selection is None
    request = decisions.queue.pending_requests[0]
    assert unit.unit_instance_id in {o.option_id for o in request.options}
    # Re-select at the production handler; both a new move and staying are available.
    chosen = DecisionResult.for_request(
        result_id="reselect", request=request, selected_option_id=unit.unit_instance_id
    )
    decisions.submit_result(chosen)
    handler = MovementPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
    )
    handler.apply_decision(state=state, decisions=decisions, result=chosen)
    status = handler.begin_phase(state=state, decisions=decisions)
    assert status.decision_request is not None
    assert {"normal_move", "remain_stationary"}.issubset(
        {o.option_id for o in status.decision_request.options}
    )
    receipt = next(
        r for r in decisions.event_log.records if r.event_type == "movement_setup_failed"
    )
    assert isinstance(receipt.payload, dict)
    assert receipt.payload["source_observation_row_id"] == "rule:03:03.02.01:1"
