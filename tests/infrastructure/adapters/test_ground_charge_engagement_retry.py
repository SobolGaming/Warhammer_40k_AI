"""Proposed admission: four native Ground Charge cases (not in the test inventory)."""

from __future__ import annotations

import json
import multiprocessing

import pytest

from tests import phase15a_charge_declaration_helpers as fixtures
from tests.charge_distance_helpers import add_modifier, select_source, select_targets
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ground_charge_candidates import (
    ChargeSearchStop,
    generate_ground_charge_candidates,
)
from warhammer40k_core.ai.ground_charge_policy import (
    GroundChargeValidationExhaustedError,
    prepare_ground_charge_policy,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRouter, payload_digest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose

pytestmark = pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground Charge preparation requires a fork-capable host.",
)

ACTOR = "player-a"
TARGET = "army-beta:enemy"
_COLUMNS = ((1, 19.75), (1, 21.55), (1, 23.35), (2.35, 26.23), (1, 26.35))
_TARGET_COLUMN = (33, 34.8, 36.6, 38.4, 40.2)


def _session(monkeypatch: pytest.MonkeyPatch, *, lateral: bool = False) -> LocalGameSession:
    if lateral:
        xs = (10, 11.8, 13.6, 15.4, 17.2)
        source = tuple(Pose.at(x, 22.2 if i % 2 == 0 else 20.4) for i, x in enumerate(xs))
        target = tuple(Pose.at(x, 33) for x in xs)
    else:
        source = tuple(Pose.at(x, y, facing_degrees=180) for x, y in _COLUMNS)
        target = tuple(Pose.at(1, y) for y in _TARGET_COLUMN)

    def formation(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
        assert origin == source[0]
        assert model_count == 5
        return source

    with monkeypatch.context() as setup:
        setup.setattr(fixtures, "compact_test_unit_poses", formation)
        lifecycle, _ = fixtures.charge_lifecycle(
            alpha_unit_ids=("source",),
            alpha_origins={"source": source[0]},
            enemy_model_poses=target,
            battle_round=2,
            game_id="mixed-ground-charge",
        )
    assert lifecycle.state is not None
    add_modifier(
        lifecycle.state, effect_id="fixture", kind="modify_dice_roll", delta=2 if lateral else -1
    )
    session = LocalGameSession(lifecycle)
    request = select_targets(session, select_source(session), (TARGET,))
    assert request.decision_type == "submit_movement_proposal"
    return session


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)


def test_rejected_rigid_charge_retries_and_commits_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(monkeypatch)
    context = _context(session)
    before = payload_digest(session.lifecycle.to_payload())
    initial = generate_ground_charge_candidates(context, raw_limit=4)
    (rigid,) = initial.candidates
    assert initial.retry_engagement is not None

    first = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=1)
    second = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=1)
    assert first.counts == second.counts
    assert first.ranked_accepted_ids == second.ranked_accepted_ids
    assert first.counts.accepted == first.counts.rejected == 1
    assert first.counts.timed_out == 0
    assert initial.geometry_work < first.counts.geometry_work < 600_000
    assert first.validations[0].candidate_id == rigid.candidate_id
    assert first.validations[0].status is LifecycleStatusKind.INVALID
    assert first.validations[1].status is LifecycleStatusKind.WAITING_FOR_DECISION
    assert payload_digest(session.lifecycle.to_payload()) == before

    registration = PolicyRouter((first.registration,)).resolve(context.route)
    action = registration.policy.choose(context)
    assert action.proposal_json is not None
    result = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        result_id="first-engagement-retry",
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


def test_successful_eligible_rigid_charge_does_not_run_engagement_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session(monkeypatch, lateral=True)
    context = _context(session)
    initial = generate_ground_charge_candidates(context, raw_limit=4)
    (rigid,) = initial.candidates
    assert initial.retry_engagement is not None
    ready = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=2)
    assert ready.ranked_accepted_ids == (rigid.candidate_id,)
    assert ready.counts.raw == ready.counts.accepted == 1
    assert ready.counts.rejected == ready.counts.timed_out == 0
    assert ready.counts.geometry_work == initial.geometry_work


@pytest.mark.parametrize("limit", ["probe", "geometry"])
def test_rejected_rigid_charge_respects_remaining_budget(
    monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    session = _session(monkeypatch)
    context = _context(session)
    before = payload_digest(session.lifecycle.to_payload())
    initial = generate_ground_charge_candidates(context, raw_limit=4)
    probe_capped = limit == "probe"
    budgets: tuple[int, ...] = (initial.geometry_work,)
    if not probe_capped:
        # Keep both the equality boundary and the one-work-unit remainder in
        # this one behavioral node.
        budgets += (initial.geometry_work + 1,)
    reason = ChargeSearchStop.VALIDATION_LIMIT if probe_capped else ChargeSearchStop.GEOMETRY_LIMIT
    for budget in budgets:
        with pytest.raises(GroundChargeValidationExhaustedError) as exc:
            prepare_ground_charge_policy(
                session,
                context,
                raw_limit=4,
                accepted_limit=1,
                geometry_limit=budget,
                validation_limit=1 if probe_capped else 4,
            )
        assert exc.value.counts.raw == exc.value.counts.rejected == 1
        assert exc.value.counts.accepted == exc.value.counts.timed_out == 0
        assert exc.value.reason is reason
        assert exc.value.counts.geometry_work == budget
        assert payload_digest(session.lifecycle.to_payload()) == before
