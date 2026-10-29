"""B04/B05: source-defined 3D disembark and genuine starting-cargo persistence."""

from dataclasses import replace

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_transport_helpers import (
    CARRIER,
    PASSENGER,
    cargo_proposal,
    reach_disembark,
    starting_cargo_session,
    submit_transport_choice,
)
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind, SetupStep
from warhammer40k_core.engine.transport_disembark_geometry import (
    _model_wholly_within_any_transport_model,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.transport_state_integrity import (
    validate_transport_cargo_state_consistency,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("distance", [3, 6])
@pytest.mark.parametrize("frame", [False, True])
def test_shared_disembark_owner_retains_vertical_and_frame_extent(
    distance: float, frame: bool
) -> None:
    carrier = Model("carrier", Pose.at(10, 10), CircularBase(2), ModelVolume(1))
    passenger = Model(
        "passenger",
        Pose.at(13, 10, 0 if frame else distance + 1),
        CircularBase(0.5),
        ModelVolume(distance + 1 if frame else 1),
        measures_every_part=frame,
    )
    context = DistanceMeasurementContext.from_models(carrier, passenger)
    assert context.target_wholly_within_distance(distance, horizontal_only=True)
    assert not context.target_wholly_within_distance(distance)
    assert not _model_wholly_within_any_transport_model(
        passenger, transport_models=(carrier,), distance_inches=distance
    )


def test_native_starting_cargo_keeps_initial_anchor_through_disembark() -> None:
    session = starting_cargo_session()
    initial = session.lifecycle.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS
    assert session.lifecycle.config.model_geometries is None
    assert_checkpoint(session)
    for _ in range(20):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if (
            state.current_setup_step is SetupStep.DEPLOY_ARMIES
            and state.battlefield_state.placed_model_ids()
        ):
            break
        submit_transport_choice(session, request)
    else:
        raise AssertionError("Partial deployment was not reached.")
    assert_checkpoint(session)
    reach_disembark(session)
    pending = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(pending).to_payload() == pending
    assert_checkpoint(session)
    proposal = cargo_proposal(session)
    result = session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id="order135-cargo:ordinary-disembark",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(PASSENGER) == proposal.attempted_placement
    assert_checkpoint(session)
    checkpoint = session.to_persistence_payload()
    assert isinstance(checkpoint, dict)
    assert checkpoint["initial_replay_lifecycle"] == initial


def test_native_setup_without_manifest_remains_restorable() -> None:
    session = starting_cargo_session(manifest=False)
    assert session.lifecycle.state is not None
    assert not session.lifecycle.state.transport_cargo_states
    assert_checkpoint(session)


@pytest.mark.parametrize(("height", "accepted"), [(1, True), (8, False)])
def test_native_frame_disembark_rejects_out_of_band_physical_body(
    height: float, accepted: bool
) -> None:
    session = starting_cargo_session(frame_height=height)
    reach_disembark(session)
    state = session.lifecycle.state
    assert state is not None
    battlefield, cargo = state.battlefield_state, tuple(state.transport_cargo_states)
    proposal = cargo_proposal(session)
    assert proposal.attempted_placement is not None
    if accepted:
        # A fitting short FRAME can retry after a rejected vertical displacement.
        # The tall FRAME above has no legal ground endpoint within three inches.
        invalid = replace(
            proposal,
            attempted_placement=replace(
                proposal.attempted_placement,
                model_placements=tuple(
                    replace(model, pose=Pose.at(model.pose.position.x, model.pose.position.y, 20))
                    for model in proposal.attempted_placement.model_placements
                ),
            ),
        )
        denied = session.submit_parameterized_payload(
            request_id=invalid.proposal_request_id,
            result_id="order135-cargo:invalid-height",
            payload=validate_json_value(invalid.to_payload()),
        )
        assert denied.status_kind is LifecycleStatusKind.INVALID
        assert state.battlefield_state == battlefield
        assert tuple(state.transport_cargo_states) == cargo
        reach_disembark(session)
        proposal = cargo_proposal(session)
    result = session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id="order135-cargo:frame-disembark",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert (result.status_kind is not LifecycleStatusKind.INVALID) is accepted, result.to_payload()
    if not accepted:
        assert state.battlefield_state == battlefield
        assert tuple(state.transport_cargo_states) == cargo
        assert pending_request(session).decision_type == "select_movement_unit"
    assert_checkpoint(session)


def test_predeployment_allowance_preserves_embarked_physical_removal_guard() -> None:
    session = starting_cargo_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    passenger = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == PASSENGER
    )
    state.battlefield_state = replace(
        state.battlefield_state,
        removed_model_ids=(passenger.own_models[0].model_instance_id,),
    )
    with pytest.raises(GameLifecycleError, match="living embarked unit models must not be removed"):
        validate_transport_cargo_state_consistency(state=state)


@pytest.mark.parametrize("boundary", ["deployed_setup", "battle"])
def test_missing_carrier_remains_invalid_after_deployment(boundary: str) -> None:
    session = starting_cargo_session()
    reach_disembark(session)
    assert session.lifecycle.state is not None
    state = GameState.from_payload(session.lifecycle.state.to_payload())
    assert state.battlefield_state is not None
    if boundary == "deployed_setup":
        from warhammer40k_core.engine.phase import GameLifecycleStage

        state.stage = GameLifecycleStage.SETUP
        state.setup_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES) + 1
    # This direct invariant check isolates the setup cutoff; the native lifecycle
    # and replay positives above retain their actual state and history throughout.
    validate_transport_cargo_state_consistency(state=state)
    state.battlefield_state = state.battlefield_state.without_unit_placement(CARRIER)
    with pytest.raises(GameLifecycleError, match="transport unit must be placed"):
        validate_transport_cargo_state_consistency(state=state)
