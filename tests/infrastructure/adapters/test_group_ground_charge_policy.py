from __future__ import annotations

import json
import multiprocessing

import pytest

from tests.charge_distance_helpers import add_modifier, select_source, select_targets
from tests.phase15a_charge_declaration_helpers import (
    charge_lifecycle,
    compact_test_unit_poses,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ground_charge_candidates import (
    ChargeSearchStop,
    GroundChargeExhaustedError,
    generate_ground_charge_candidates,
)
from warhammer40k_core.ai.ground_charge_policy import prepare_ground_charge_policy
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRouter, payload_digest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

ACTOR = "player-a"
TARGET = "army-beta:enemy"


@pytest.fixture
def group_charge() -> LocalGameSession:
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        game_id="five-ground-charge",
    )
    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="fixture", kind="modify_dice_roll", delta=10)
    session = LocalGameSession(lifecycle)
    request = select_targets(session, select_source(session), (TARGET,))
    assert request.decision_type == "submit_movement_proposal"
    return session


def test_group_charge_generates_distinct_complete_witnesses(group_charge: LocalGameSession) -> None:
    view = group_charge.view(viewer_player_id=ACTOR)
    context = PlayerDecisionContext.from_view(view, choice_seed=1)
    generated = generate_ground_charge_candidates(context, raw_limit=4)
    assert generated == generate_ground_charge_candidates(
        PlayerDecisionContext.from_view(view, choice_seed=2), raw_limit=4
    )
    assert generated.stop is ChargeSearchStop.RAW_LIMIT
    source = view["unit_display_by_id"]["army-alpha:source"]
    endpoints: set[tuple[Pose, ...]] = set()
    for candidate in generated.candidates:
        assert candidate.action.proposal_json is not None
        action = json.loads(candidate.action.proposal_json)
        assert action["charge_target_unit_instance_ids"] == [TARGET]
        witness = PathWitness.from_payload(action["witness"])
        assert set(witness.model_ids()) == set(source["model_instance_ids"])
        endpoints.add(tuple(poses[-1] for _, poses in witness.model_paths))
    assert len(endpoints) == 4

    with pytest.raises(GroundChargeExhaustedError) as caught:
        generate_ground_charge_candidates(context, geometry_limit=1)
    assert caught.value.reason is ChargeSearchStop.GEOMETRY_LIMIT
    assert caught.value.counts.geometry_work == 1


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
def test_group_charge_commits_a_native_accept(group_charge: LocalGameSession) -> None:
    session = group_charge
    context = PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)
    before = payload_digest(session.lifecycle.to_payload())
    prepared = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=2)
    assert payload_digest(session.lifecycle.to_payload()) == before
    assert prepared.counts.accepted == 2
    assert prepared.counts.timed_out == 0

    registration = PolicyRouter((prepared.registration,)).resolve(context.route)
    action = registration.policy.choose(context)
    assert action.proposal_json is not None
    assert payload_digest(action.proposal_json) == prepared.ranked_accepted_ids[0]
    result = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        result_id="group-charge",
        payload=json.loads(action.proposal_json),
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        sum(
            event.event_type == "charge_move_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
