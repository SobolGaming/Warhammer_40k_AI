"""All otherwise-eligible units constrain passing, independently of ordering band.

The restored canonical fixtures below isolate decision admission and deliberate
stale-state validation; they do not establish native pregame reachability.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_counteroffensive_helpers import actual_fought_events, army_id, other_player
from tests.order135_fight_pass_helpers import native_pass_session, submit_pass_scene_choice
from tests.phase15c_fight_order_helpers import (
    advance_to_fight_order_request,
    fight_lifecycle,
)

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    eligible_fight_contexts_for_player,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
def test_nearby_remaining_unit_prevents_fights_first_pass(actor: str) -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("first", "near") if actor == "player-a" else ("enemy",),
        enemy_unit_ids=("enemy",) if actor == "player-a" else ("first", "near"),
        origins={
            "first": Pose.at(10, 10),
            "near": Pose.at(10, 30),
            "enemy": Pose.at(11.8, 30),
        },
        game_id=f"order135-pass-near:{actor}",
        charge_fights_first_unit_keys=("first",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    request = advance_to_fight_order_request(lifecycle)
    assert request.decision_type == "select_fight_activation"
    assert request.actor_id == actor
    state = lifecycle.state
    assert state is not None
    fight = state.fight_phase_state
    assert fight is not None
    policy = lifecycle.config.ruleset_descriptor.fight_policy
    band = eligible_fight_contexts_for_player(
        state=state, fight_state=fight, player_id=actor, policy=policy
    )
    eligible = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight,
        player_id=actor,
        policy=policy,
        respect_ordering_band=False,
    )
    assert [context.unit_instance_id for context in band] == [units["first"].unit_instance_id]
    assert band[0].more_than_pass_distance_from_all_enemies
    assert {context.unit_instance_id for context in eligible} == {
        units["first"].unit_instance_id,
        units["near"].unit_instance_id,
    }
    assert any(not context.more_than_pass_distance_from_all_enemies for context in eligible)
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID not in {option.option_id for option in request.options}


def test_original_five_model_pass_fixture_rejects_pass() -> None:
    # Preserve the old regression's exact geometry and eligibility as a negative control.
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=("alpha-first", "alpha-remaining"),
        enemy_unit_ids=("enemy",),
        origins={
            "alpha-first": Pose.at(10, 20),
            "alpha-remaining": Pose.at(10, 40),
            "enemy": Pose.at(13, 40),
        },
        game_id="phase15c-pass-before-remaining",
        charge_fights_first_unit_keys=("alpha-first",),
    )
    request = advance_to_fight_order_request(lifecycle)
    assert request.actor_id == "player-a"
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID not in {option.option_id for option in request.options}


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
def test_newly_nearby_lower_band_unit_invalidates_offered_pass_atomically(actor: str) -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("first", "near") if actor == "player-a" else ("enemy",),
        enemy_unit_ids=("enemy",) if actor == "player-a" else ("first", "near"),
        origins={
            "first": Pose.at(10, 10),
            "near": Pose.at(10, 30),
            "enemy": Pose.at(30, 30),
        },
        game_id=f"order135-pass-drift:{actor}",
        charge_fights_first_unit_keys=("first",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    request = advance_to_fight_order_request(lifecycle)
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        result_id=f"{request.request_id}:stale-pass",
        selected_option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    ).to_result(request)
    state = lifecycle.state
    assert state is not None
    field = state.battlefield_state
    assert field is not None
    enemy = field.unit_placement_by_id(units["enemy"].unit_instance_id)
    # Deliberate stale-state fault injection: the band-specific option snapshot
    # remains unchanged, but an otherwise eligible Remaining unit is now nearby.
    state.replace_battlefield_state(
        field.with_unit_placement(
            replace(
                enemy,
                model_placements=(replace(enemy.model_placements[0], pose=Pose.at(11.8, 30)),),
            )
        )
    )
    before = lifecycle.to_payload()
    status = lifecycle.submit_decision(result)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {
        "invalid_reason": "invalid_fight_activation_result",
        "field": "eligible_to_fight_pass",
    }
    assert lifecycle.to_payload() == before
    # Undo only the injected drift, then use the original finite request for legal retry.
    state.replace_battlefield_state(field)
    accepted = lifecycle.submit_decision(result)
    assert accepted.status_kind is not LifecycleStatusKind.INVALID


@pytest.mark.parametrize(("gap", "available"), [(4.999999, False), (5.0, False), (5.000001, True)])
def test_pass_distance_boundary_is_strict(gap: float, available: bool) -> None:
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=("first",),
        enemy_unit_ids=("enemy",),
        origins={"first": Pose.at(10, 20), "enemy": Pose.at(10 + 40 / 25.4 + gap, 20)},
        game_id=f"order135-pass-boundary:{gap}",
        charge_fights_first_unit_keys=("first",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    request = advance_to_fight_order_request(lifecycle)
    assert (ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {o.option_id for o in request.options}) is available


@pytest.mark.parametrize("passer", ["player-a", "player-b"])
@pytest.mark.parametrize("nearby", [False, True])
def test_native_pass_after_shared_charge_target_dies(
    passer: str, nearby: bool, tmp_path: Path
) -> None:
    session = native_pass_session(passer=passer, nearby=nearby)
    waiting = f"{army_id(passer)}:two"
    trace: list[tuple[str, str, str | None, list[str], str | None, tuple[str, ...] | None]] = []
    for _ in range(300):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        fight = state.fight_phase_state
        trace.append(
            (
                request.request_id,
                request.decision_type,
                request.actor_id,
                [o.option_id for o in request.options],
                None if fight is None else fight.current_ordering_band.value,
                None if fight is None else fight.fight_order_state.selected_to_fight_unit_ids,
            )
        )
        assert state.battle_round <= 2, json.dumps(
            {
                "trace": trace,
                "charge_and_movement": [
                    e.to_payload()
                    for e in session.lifecycle.decision_controller.event_log.records
                    if "charge" in e.event_type or "movement_proposal" in e.event_type
                ],
            },
            indent=2,
        )
        if (
            state.battle_round == 2
            and state.active_player_id == passer
            and request.decision_type == "select_fight_activation"
            and fight is not None
            and fight.current_ordering_band.value == "fights_first"
            and f"{army_id(passer)}:one" in fight.fight_order_state.selected_to_fight_unit_ids
        ):
            break
        submit_pass_scene_choice(session, request, passer=passer, nearby=nearby)
    else:
        raise AssertionError("Two actual chargers did not reach the surviving-unit pass boundary")
    assert request.actor_id == passer
    policy = session.lifecycle.config.ruleset_descriptor.fight_policy
    band = eligible_fight_contexts_for_player(
        state=state, fight_state=fight, player_id=passer, policy=policy
    )
    assert [c.unit_instance_id for c in band] == [waiting]
    assert band[0].more_than_pass_distance_from_all_enemies
    all_eligible = eligible_fight_contexts_for_player(
        state=state, fight_state=fight, player_id=passer, policy=policy, respect_ordering_band=False
    )
    assert {c.unit_instance_id for c in all_eligible} == (
        {waiting, f"{army_id(passer)}:three"} if nearby else {waiting}
    )
    assert any(not c.more_than_pass_distance_from_all_enemies for c in all_eligible) is nearby
    assert (ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {o.option_id for o in request.options}) is (
        not nearby
    )
    assert state.battlefield_state is not None
    assert any(
        model_id.startswith(f"{army_id(other_player(passer))}:one:")
        for model_id in state.battlefield_state.removed_model_ids
    )
    assert any(
        isinstance(event.payload, dict)
        and event.payload["attack_sequence_id"] is not None
        and isinstance(event.payload["activation_selection"], dict)
        and event.payload["activation_selection"]["unit_instance_id"] == f"{army_id(passer)}:one"
        for event in actual_fought_events(session)
    )
    assert_checkpoint(session)
    (tmp_path / "pending.json").write_text(json.dumps(session.to_persistence_payload()))
    recovered = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    forked = session.fork()
    for continuation in (session, recovered, forked):
        assert continuation.advance_until_decision_or_terminal().decision_request == request
        option = request.options[0].option_id if nearby else ELIGIBLE_TO_FIGHT_PASS_OPTION_ID
        status = continuation.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:pass-control",
            option_id=option,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        if not nearby:
            for _ in range(8):
                next_request = continuation.advance_until_decision_or_terminal().decision_request
                assert next_request is not None
                if next_request.decision_type == "select_fight_activation":
                    break
                assert next_request.decision_type in {
                    "use_stratagem",
                    "submit_stratagem_target_proposal",
                }
                submit_pass_scene_choice(continuation, next_request, passer=passer, nearby=nearby)
            else:
                raise AssertionError("Legal pass did not hand selection to Remaining Combats")
            assert next_request.actor_id == other_player(passer)
            assert isinstance(next_request.payload, dict)
            assert next_request.payload["ordering_band"] == "remaining_combats"
            assert any(
                isinstance(o.payload, dict)
                and o.payload.get("unit_instance_id") == f"{army_id(other_player(passer))}:three"
                for o in next_request.options
            )
    assert recovered.to_persistence_payload() == session.to_persistence_payload()
    assert forked.to_persistence_payload() == session.to_persistence_payload()
    assert_checkpoint(session)
    (tmp_path / "completed.json").write_text(json.dumps(session.to_persistence_payload()))
    (tmp_path / "public-request-trace.json").write_text(json.dumps(trace, indent=2))
