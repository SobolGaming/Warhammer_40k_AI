"""Clause assertions for Heavy's accepted movement and Category 07 phase order."""

from __future__ import annotations

import json
from math import isclose, sqrt
from typing import cast

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay, clause_session
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.weapon_abilities import HEAVY_RULE_ID
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("flying", [False, True])
def test_heavy_accepted_vertical_movement_reaches_facade_attack(flying: bool) -> None:
    session = clause_session(phase=BattlePhase.MOVEMENT, fly=True)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="army-alpha:mover", result_id="select-mover"
    )
    request = pending_request(session)
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("movement_phase_action") == "normal_move"
        and (option.payload["movement_mode"] == "fly_take_to_skies") is flying
    )
    session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="select-flight"
    )
    request = pending_request(session)
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(model.pose.position.x + 1, model.pose.position.y, 1.5),
                    Pose.at(model.pose.position.x + 2, model.pose.position.y),
                ),
            )
            for model in placement.model_placements
        )
    )
    assert isinstance(option.payload, dict)
    payload = validate_json_value(
        MovementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=move.proposal_kind,
            unit_instance_id=move.unit_instance_id,
            movement_phase_action="normal_move",
            movement_mode=cast(str, option.payload["movement_mode"]),
            witness=witness,
        ).to_payload()
    )
    before = session.to_persistence_payload()
    malformed = cast(dict[str, JsonValue], json.loads(json.dumps(payload)))
    malformed["proposal_request_id"] = "stale"
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="invalid-move", payload=malformed
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="move", payload=payload
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert len(state.model_movement_history) == 5
    assert all(
        isclose(row.distance_inches, 2 if flying else sqrt(13), abs_tol=1e-9)
        for row in state.model_movement_history
    )
    assert state.current_battle_phase is BattlePhase.SHOOTING
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    session = LocalGameSession.from_persistence_payload(checkpoint)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="army-alpha:mover", result_id="select-shooter"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="select-type"
    )
    request = pending_request(session)
    proposal = _proposal_from_request(
        request=request,
        target_unit_id="army-beta:enemy",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="shoot",
        payload=validate_json_value(proposal.to_payload()),
    )
    for _ in range(30):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "attack_sequence_completed" for event in events):
            break
        submit_fixture_request(session, pending_request(session))
    events = session.lifecycle.decision_controller.event_log.records
    accepted = next(
        event.payload for event in events if event.event_type == "shooting_declaration_accepted"
    )
    assert isinstance(accepted, dict)
    pools = cast(list[dict[str, JsonValue]], accepted["attack_pools"])
    assert pools
    assert all(pool["hit_roll_modifier"] == int(flying) for pool in pools)
    assert all(
        (HEAVY_RULE_ID in cast(list[str], pool["targeting_rule_ids"])) is flying for pool in pools
    )
    hits = [
        event.payload
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "hit"
    ]
    assert hits
    for hit in hits:
        assert isinstance(hit, dict)
        roll = cast(dict[str, JsonValue], hit["payload"])
        assert roll["capped_modifier"] == int(flying)
        assert roll["final_roll"] == cast(int, roll["unmodified_roll"]) + int(flying)
    assert_persistence_viewers_replay(session)


def test_category07_facade_round_turn_phase_order_and_restore() -> None:
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    session = clause_session(phase=BattlePhase.COMMAND)
    restored = False
    for _ in range(100):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if state.battle_round == 3:
            break
        if not restored and state.active_player_id == "player-b":
            checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
            for request_id, option_id in (
                ("stale", request.options[0].option_id),
                (request.request_id, "unknown"),
            ):
                with pytest.raises((GameLifecycleError, DecisionError)):
                    session.submit_option(
                        request_id=request_id, option_id=option_id, result_id="invalid"
                    )
                assert session.to_persistence_payload() == checkpoint
            session = LocalGameSession.from_persistence_payload(checkpoint)
            restored = True
        result_id = request.request_id + ":order97"
        if request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=result_id,
                payload=stratagem_decline_payload(),
            )
        else:
            assert request.decision_type in {
                "select_movement_unit",
                "select_movement_action",
                "select_shooting_unit",
                "select_charging_unit",
                "use_stratagem",
            }, request
            options = [
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or option.option_id in {"remain_stationary", "decline"}
            ]
            option = options[0] if options else request.options[0]
            status = session.submit_option(
                request_id=request.request_id, result_id=result_id, option_id=option.option_id
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert restored
    state = session.lifecycle.state
    assert state is not None
    assert state.battle_round == 3
    assert state.active_player_id == "player-a"
    windows: list[tuple[JsonValue, JsonValue, JsonValue, JsonValue]] = []
    for event in session.lifecycle.decision_controller.event_log.records:
        if event.event_type != "timing_window_opened":
            continue
        payload = cast(dict[str, JsonValue], event.payload)
        window = cast(dict[str, JsonValue], payload["timing_window"])
        if cast(int, window["battle_round"]) > 2:
            continue
        descriptor = cast(dict[str, JsonValue], window["descriptor"])
        windows.append(
            (
                window["battle_round"],
                window["active_player_id"],
                descriptor["trigger_kind"],
                window["phase"],
            )
        )
        if descriptor["trigger_kind"] in {"end_turn", "end_battle_round"}:
            assert payload["resolution_order"] == ["non_mission_rules", "mission_rules"]
    expected: list[tuple[int, str, str, str | None]] = []
    for round_number in (1, 2):
        expected.append((round_number, "player-a", "start_battle_round", None))
        for player in ("player-a", "player-b"):
            expected.append((round_number, player, "start_turn", None))
            for phase in ("command", "movement", "shooting", "charge", "fight"):
                expected.extend(
                    (
                        (round_number, player, "start_phase", phase),
                        (round_number, player, "end_phase", phase),
                    )
                )
            expected.append((round_number, player, "end_turn", None))
        expected.append((round_number, "player-a", "end_battle_round", None))
    assert windows == expected
    events = session.lifecycle.decision_controller.event_log.records
    completions = [
        (index, cast(dict[str, JsonValue], event.payload))
        for index, event in enumerate(events)
        if event.event_type == "battle_phase_completed"
    ][:20]
    assert [payload["completed_phase"] for _, payload in completions] == [
        phase for _ in range(4) for phase in ("command", "movement", "shooting", "charge", "fight")
    ]
    previous_completion = -1
    for completion_index, completion in completions:
        boundaries: list[JsonValue] = []
        for event in events[previous_completion + 1 : completion_index]:
            if event.event_type != "timing_window_opened":
                continue
            payload = cast(dict[str, JsonValue], event.payload)
            window = cast(dict[str, JsonValue], payload["timing_window"])
            descriptor = cast(dict[str, JsonValue], window["descriptor"])
            if window["phase"] == completion["completed_phase"]:
                boundaries.append(descriptor["trigger_kind"])
        assert boundaries == ["start_phase", "end_phase"]
        assert (
            completion["next_phase"]
            == {
                "command": "movement",
                "movement": "shooting",
                "shooting": "charge",
                "charge": "fight",
                "fight": "command",
            }[cast(str, completion["completed_phase"])]
        )
        previous_completion = completion_index
    assert_persistence_viewers_replay(session)


def test_fight_facade_completes_source_steps_in_order() -> None:
    session = clause_session(phase=BattlePhase.FIGHT)
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    snapshots: list[list[tuple[str, str]]] = []
    for event in session.lifecycle.decision_controller.event_log.records:
        if event.event_type not in {
            "fight_phase_started",
            "fight_step_completed",
            "fight_phase_completed",
        }:
            continue
        payload = cast(dict[str, JsonValue], event.payload)
        state = cast(dict[str, JsonValue], payload["fight_phase_state"])
        steps = cast(list[dict[str, str]], state["step_states"])
        snapshots.append([(step["step"], step["status"]) for step in steps])
    assert snapshots == [
        [
            ("start", "complete"),
            ("pile_in", "active"),
            ("fight", "pending"),
            ("consolidate", "pending"),
            ("end", "pending"),
        ],
        [
            ("start", "complete"),
            ("pile_in", "complete"),
            ("fight", "complete"),
            ("consolidate", "active"),
            ("end", "pending"),
        ],
        [
            ("start", "complete"),
            ("pile_in", "complete"),
            ("fight", "complete"),
            ("consolidate", "complete"),
            ("end", "complete"),
        ],
    ]
    assert_persistence_viewers_replay(session)


def test_charge_facade_completes_first_unit_before_selecting_second_once() -> None:
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle
    from tests.phase15a_charge_test_support import (
        _charge_path_witness_for_unit,
        _compact_test_unit_poses,
    )

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.phases.charge import ChargeMoveProposal

    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        alpha_origins={"intercessor-1": Pose.at(10, 20), "intercessor-2": Pose.at(10, 30)},
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(10, 25), model_count=5),
        game_id="order97-charge-once",
    )
    session = LocalGameSession(lifecycle)
    initial = pending_request(session)
    first = units["intercessor-1"].unit_instance_id
    second = units["intercessor-2"].unit_instance_id
    assert {first, second} <= {option.option_id for option in initial.options}
    session.submit_option(request_id=initial.request_id, option_id=first, result_id="first")
    reroll = pending_request(session)
    assert reroll.decision_type == "use_stratagem"
    session.submit_option(
        request_id=reroll.request_id,
        option_id="decline_stratagem_window",
        result_id="decline-reroll",
    )
    targets = pending_request(session)
    assert targets.decision_type == "select_charge_targets"
    target_option = next(
        option
        for option in targets.options
        if isinstance(option.payload, dict)
        and option.payload["target_ids"] == [units["enemy"].unit_instance_id]
    )
    session.submit_option(
        request_id=targets.request_id, option_id=target_option.option_id, result_id="first:targets"
    )
    request = pending_request(session)
    assert request.decision_type == "submit_movement_proposal"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    before = session.to_persistence_payload()
    with pytest.raises((GameLifecycleError, DecisionError)):
        session.submit_option(
            request_id=initial.request_id, option_id=second, result_id="premature-second"
        )
    assert session.to_persistence_payload() == before
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="first-charge-move",
        payload=validate_json_value(
            ChargeMoveProposal(
                proposal_request_id=request.request_id,
                proposal_kind=move.proposal_kind,
                unit_instance_id=first,
                movement_phase_action="charge_move",
                movement_mode=MovementMode.CHARGE,
                charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
                witness=_charge_path_witness_for_unit(
                    lifecycle, unit_instance_id=first, dx=0, dy=3
                ),
            ).to_payload()
        ),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    next_request = pending_request(session)
    assert next_request.decision_type == "select_charging_unit"
    assert {option.option_id for option in next_request.options} == {
        second,
        "complete_charge_phase",
    }
    session.submit_option(
        request_id=next_request.request_id, option_id=second, result_id="second-charge"
    )
    events = lifecycle.decision_controller.event_log.records
    completed = next(
        i for i, event in enumerate(events) if event.event_type == "charge_move_completed"
    )
    selected = [i for i, event in enumerate(events) if event.event_type == "charging_unit_selected"]
    assert len(selected) == 2
    assert selected[0] < completed < selected[1]
    assert_persistence_viewers_replay(session)
