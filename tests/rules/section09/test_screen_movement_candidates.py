"""Stage 2 movement candidates use the existing viewer decisions and native rules."""

import json

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import movement_case, select
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError
from warhammer40k_core.ai.screen_movement_candidates import (
    MAX_RETREAT_PROPOSALS,
    ScreenMovementGap,
    ScreenMovementGapReason,
    generate_retreat_proposals,
    generate_screen_movement_options,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_model import FallBackModeKind


@pytest.mark.parametrize("mode", tuple(FallBackModeKind))
def test_screen_options_and_retreat_paths_use_native_requests(
    section09_definitions: Section02Definitions, mode: FallBackModeKind
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    request = select(session, unit)
    actor = request.actor_id
    assert actor is not None
    viewer = ViewerContext.for_player(actor)
    enemy = next(player for player in state.player_ids if player != actor)
    with pytest.raises(PolicyError, match="own pending actor request"):
        PlayerDecisionContext.from_view(session.view(viewer_player_id=enemy), choice_seed=0)
    context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=0
    )
    options = generate_screen_movement_options(context)
    assert options.hold.option_id == "remain_stationary"
    assert {mode for mode, _ in options.fall_back} == set(FallBackModeKind)
    with pytest.raises(ScreenMovementGap) as wrong_route:
        generate_retreat_proposals(context)
    assert wrong_route.value.reason is ScreenMovementGapReason.NO_ORDINARY_FALL_BACK_REQUEST

    retreat = dict(options.fall_back)[mode]
    assert retreat.option_id is not None
    assert retreat.observation_hash == context.observation_hash
    status = session.submit_viewer_option(
        viewer=viewer,
        request_id=retreat.request_id,
        option_id=retreat.option_id,
        result_id="screen-test:retreat",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=0
    )
    generated = generate_retreat_proposals(context)
    assert 1 <= len(generated) <= MAX_RETREAT_PROPOSALS
    assert generated == generate_retreat_proposals(context)
    assert len(set(generated)) == len(generated)
    model_ids = {model.model_instance_id for model in unit.own_models}
    for action in generated:
        assert action.proposal_json is not None
        assert action.actor_id == actor
        assert action.request_id == context.request["request_id"]
        assert action.observation_hash == context.observation_hash
        proposal = MovementProposalPayload.from_payload(json.loads(action.proposal_json))
        assert proposal.fall_back_mode == mode
        assert set(proposal.witness.model_ids()) == model_ids
    assert context.observation == session.view_for_context(viewer=viewer)
    # The fixture places the opponent north of the unit. Select a generated
    # southbound witness to test submission under each of the two native modes.
    for action in generated:
        assert action.proposal_json is not None
        payload = json.loads(action.proposal_json)
        witness = MovementProposalPayload.from_payload(payload).witness
        start, end = witness.model_paths[0][1]
        if end.position.x == start.position.x and end.position.y < start.position.y:
            break
    else:
        pytest.fail("No southbound retreat generated.")
    status = session.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=action.request_id,
        result_id="screen-test:path",
        payload=payload,
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    hold, _, hold_unit = movement_case(section09_definitions, engaged=True)
    select(hold, hold_unit)
    hold_context = PlayerDecisionContext.from_view(
        hold.view_for_context(viewer=viewer), choice_seed=0
    )
    hold_action = generate_screen_movement_options(hold_context).hold
    assert hold_action.option_id is not None
    status = hold.submit_viewer_option(
        viewer=viewer,
        request_id=hold_action.request_id,
        option_id=hold_action.option_id,
        result_id="screen-test:hold",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION


def test_screen_options_require_an_issued_fall_back_alternative(
    section09_definitions: Section02Definitions,
) -> None:
    session, _, unit = movement_case(section09_definitions)
    request = select(session, unit)
    assert request.actor_id is not None
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id=request.actor_id), choice_seed=0
    )
    with pytest.raises(ScreenMovementGap) as gap:
        generate_screen_movement_options(context)
    assert gap.value.reason is ScreenMovementGapReason.NO_HOLD_RETREAT_OFFER
