"""Order 49: reroll choices share dice, Stratagem and Charge authority."""

from __future__ import annotations

import json
from typing import cast

import pytest
from tests.charge_distance_helpers import request_from
from tests.charge_reroll_helpers import heroic_session
from tests.heroic_intervention_helpers import drive_heroic_charge_choices
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.phase15a_charge_test_support import (
    _submit_end_charge_heroic_target,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("accept", [False, True])
def test_ordinary_charge_command_reroll_restores_and_rolls_both_dice(accept: bool) -> None:
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("source", "next"),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        game_id="order49-command-reroll",
    )
    state = lifecycle.state
    assert state is not None
    state.gain_command_points(
        player_id="player-a",
        amount=2,
        source_id="order49-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    session = LocalGameSession(lifecycle)
    selection = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=selection.request_id,
            option_id=units["source"].unit_instance_id,
            result_id="order49-select",
        )
    )
    assert request.decision_type == "use_stratagem"
    assert state.charge_phase_state is not None
    assert not state.charge_phase_state.distance_states
    restored = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    )
    session = LocalGameSession(restored)
    option_id = next(
        o.option_id for o in request.options if o.option_id != "decline_stratagem_window"
    )
    if not accept:
        option_id = "decline_stratagem_window"
    session.submit_option(
        request_id=request.request_id, option_id=option_id, result_id="order49-reroll-choice"
    )
    assert restored.state is not None
    assert restored.state.command_point_total("player-a") == 2 - int(accept)
    rolls = [
        cast(dict[str, JsonValue], event.payload)
        for event in restored.decision_controller.event_log.records
        if event.event_type == "charge_roll_resolved"
    ]
    assert len(rolls) == 1
    result = cast(dict[str, JsonValue], rolls[0]["roll_result"])
    roll = cast(dict[str, JsonValue], result["roll_state"])
    rerolls = cast(list[dict[str, JsonValue]], roll["rerolls"])
    assert len(rerolls) == int(accept)
    if accept:
        assert rerolls[0]["selected_indices"] == [0, 1]
        use = restored.state.stratagem_use_records[-1]
        assert use.targeted_unit_instance_ids == (units["source"].unit_instance_id,)
        assert use.affected_unit_instance_ids == use.targeted_unit_instance_ids


def test_heroic_intervention_natural_charge_reroll_remains_available() -> None:
    session, unit_id = heroic_session(natural=True)
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        _submit_end_charge_heroic_target(
            session,
            request=request,
            target_unit_instance_id=unit_id,
            result_id="order49-heroic",
        )
    )
    assert request.decision_type == "select_dice_reroll"
    assert tuple(option.option_id for option in request.options) == ("decline", "reroll:0,1")
    assert all("command-reroll" not in option.option_id for option in request.options)


@pytest.mark.parametrize("accept", [False, True])
def test_heroic_native_reroll_restores_replays_and_never_spends_second_cp(accept: bool) -> None:
    from tests.phase15a_charge_test_support import _submit_heroic_intervention_no_move

    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session, unit_id = heroic_session(natural=True)
    initial = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        _submit_end_charge_heroic_target(
            session, request=initial, target_unit_instance_id=unit_id, result_id="hi-use"
        )
    )
    restored = LocalGameSession(
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
        )
    )
    option_id = request.options[-1 if accept else 0].option_id
    for branch in (session, restored):
        movement = request_from(
            drive_heroic_charge_choices(
                branch,
                branch.submit_option(
                    request_id=request.request_id, option_id=option_id, result_id="hi-native"
                ),
                unit_id=unit_id,
                result_prefix="hi-native",
            )
        )
        assert movement.decision_type == "submit_movement_proposal"
        from warhammer40k_core.engine.movement_proposals import MovementProposalRequest

        context = MovementProposalRequest.from_decision_request_payload(movement.payload).context
        assert isinstance(context, dict)
        roll = cast(
            dict[str, JsonValue], cast(dict[str, JsonValue], context["charge_roll"])["roll_state"]
        )
        assert len(cast(list[JsonValue], roll["rerolls"])) == int(accept)
        if accept:
            assert cast(list[dict[str, JsonValue]], roll["rerolls"])[0]["selected_indices"] == [
                0,
                1,
            ]
        state = branch.lifecycle.state
        assert state is not None
        assert state.command_point_total("player-a") == 1
        assert [use.handler_id for use in state.stratagem_use_records] == [
            "core:heroic-intervention"
        ]
        _submit_heroic_intervention_no_move(
            branch, movement_request=movement, result_id="hi-no-move"
        )
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="hi-replay")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("accept", [False, True])
def test_ordinary_native_reroll_precedes_command_and_prevents_rerolling_twice(accept: bool) -> None:
    from tests.charge_reroll_helpers import ordinary_session

    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session, unit_id = ordinary_session(natural=True)
    select = request_from(session.advance_until_decision_or_terminal())
    native = request_from(
        session.submit_option(
            request_id=select.request_id, option_id=unit_id, result_id="native-select"
        )
    )
    assert native.decision_type == "select_dice_reroll"
    assert tuple(option.option_id for option in native.options) == ("decline", "reroll:0,1")
    after = request_from(
        session.submit_option(
            request_id=native.request_id,
            option_id=native.options[-1 if accept else 0].option_id,
            result_id="native-choice",
        )
    )
    state = session.lifecycle.state
    assert state is not None
    if accept:
        assert after.decision_type == "select_charge_targets"
        assert state.command_point_total("player-a") == 2
    else:
        assert after.decision_type == "use_stratagem"
        after = request_from(
            session.submit_option(
                request_id=after.request_id,
                option_id=next(
                    o.option_id for o in after.options if o.option_id != "decline_stratagem_window"
                ),
                result_id="command-after-native-decline",
            )
        )
        assert after.decision_type == "select_charge_targets"
        assert state.command_point_total("player-a") == 1
    resolved = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "charge_roll_resolved"
    ]
    assert len(resolved) == 1
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="native-replay")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("attached", [False, True])
def test_command_charge_target_is_canonical_rules_unit(attached: bool) -> None:
    from tests.charge_reroll_helpers import ordinary_session

    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    session, unit_id = ordinary_session(natural=False, attached=attached)
    select = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=select.request_id, option_id=unit_id, result_id="canonical-select"
        )
    )
    option = next(o for o in request.options if o.option_id != "decline_stratagem_window")
    assert isinstance(option.payload, dict)
    target = cast(dict[str, JsonValue], option.payload["target_binding"])
    assert target["target_unit_instance_id"] == unit_id
    for viewer in ("player-a", "player-b"):
        visible = json.dumps(session.view(viewer_player_id=viewer))
        delta = json.dumps(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "object at 0x" not in visible + delta
        assert unit_id in visible


@pytest.mark.parametrize(
    "field", ["charge_action_id", "dice_roll_state", "affected_unit_instance_id"]
)
def test_charge_command_context_drift_rejects_before_queue_pop(field: str) -> None:
    from tests.charge_reroll_helpers import ordinary_session

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, unit_id = ordinary_session(natural=False)
    select = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=select.request_id, option_id=unit_id, result_id="drift-select"
        )
    )
    payload = cast(dict[str, JsonValue], request.payload)
    context = cast(dict[str, JsonValue], payload["stratagem_context"])
    trigger = cast(dict[str, JsonValue], context["trigger_payload"])
    trigger[field] = "forged"
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        option_id="decline_stratagem_window",
        result_id="drift-choice",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    with pytest.raises(ValueError, match=r"Charge|reroll|decision_requested"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, json.loads(json.dumps(before))))


def test_heroic_intervention_spends_target_slot_even_without_natural_reroll() -> None:
    from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
    from warhammer40k_core.engine.stratagems import (
        StratagemEligibilityContext,
        stratagem_use_options_for_handler_from_index,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    session, unit_id = heroic_session(natural=False)
    request = request_from(session.advance_until_decision_or_terminal())
    movement = request_from(
        _submit_end_charge_heroic_target(
            session, request=request, target_unit_instance_id=unit_id, result_id="no-native-hi"
        )
    )
    context = MovementProposalRequest.from_decision_request_payload(movement.payload).context
    assert isinstance(context, dict)
    roll = DiceRollState.from_payload(
        cast(DiceRollStatePayload, cast(dict[str, JsonValue], context["charge_roll"])["roll_state"])
    )
    assert not roll.original_result.spec.reroll_forbidden_rule_ids
    state = session.lifecycle.state
    assert state is not None
    eligibility_context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        timing_window_id="hi-command-check",
        trigger_payload={
            "dice_roll_state": cast(JsonValue, roll.to_payload()),
            "affected_unit_instance_id": unit_id,
        },
    )
    assert not stratagem_use_options_for_handler_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=eligibility_context,
        handler_id="core:command-reroll",
    )
    assert state.command_point_total("player-a") == 1


@pytest.mark.parametrize("native", [False, True])
def test_battle_shock_blocks_command_but_not_natural_charge_reroll(native: bool) -> None:
    from tests.charge_reroll_helpers import ordinary_session

    from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session, unit_id = ordinary_session(natural=native)
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    state.replace_battle_shock_state(
        (
            [unit_id],
            [
                BattleShockedUnitState(
                    player_id="player-a",
                    unit_instance_id=unit_id,
                    model_instance_ids=tuple(m.model_instance_id for m in view.alive_models()),
                    source_result_id="order49-battle-shock-fixture",
                    battle_round_started=1,
                )
            ],
        )
    )
    select = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=select.request_id, option_id=unit_id, result_id="shocked-select"
        )
    )
    assert request.decision_type == ("select_dice_reroll" if native else "select_charge_targets")
    assert state.command_point_total("player-a") == 2


@pytest.mark.parametrize("native", [False, True])
def test_removing_reroll_origin_cannot_bypass_prevalidation(native: bool) -> None:
    from tests.charge_reroll_helpers import ordinary_session

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, unit_id = ordinary_session(natural=native)
    select = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=select.request_id, option_id=unit_id, result_id="origin-select"
        )
    )
    payload = cast(dict[str, JsonValue], request.payload)
    if native:
        payload.pop("charge_context")
    else:
        context = cast(dict[str, JsonValue], payload["stratagem_context"])
        trigger = cast(dict[str, JsonValue], context["trigger_payload"])
        trigger.pop("charge_action_id")
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        option_id="decline" if native else "decline_stratagem_window",
        result_id="missing-origin",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
