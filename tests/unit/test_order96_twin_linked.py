"""C24-11: every optional wound reroll needs a submitted player decision."""

from __future__ import annotations

import json
from typing import cast

import pytest
from tests.absent_strength_helpers import strength_session
from tests.lethal_hits_helpers import attack_completed, attack_steps
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.twin_linked_helpers import complete_optional_attack, reach_wound_reroll, submit_next

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.weapon_abilities import TWIN_LINKED_RULE_ID


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("choice", ["decline", "reroll:0"])
def test_optional_twin_linked_all_wounds_restore_viewers_and_exact_replay(
    phase: BattlePhase, choice: str
) -> None:
    session = strength_session(phase)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    requests: list[dict[str, JsonValue]] = []
    values: set[int] = set()
    restored_once = False
    for _ in range(100):
        if attack_completed(session):
            break
        request = pending_request(session)
        if request.decision_type != "select_dice_reroll":
            submit_fixture_request(session, request)
            continue
        payload = cast(dict[str, JsonValue], request.payload)
        assert payload["source_rule_id"] == TWIN_LINKED_RULE_ID
        assert [option.option_id for option in request.options] == ["decline", "reroll:0"]
        context = cast(dict[str, JsonValue], payload["attack_context"])
        roll = cast(dict[str, JsonValue], context["wound_roll_state"])
        assert roll["rerolls"] == []
        values.add(cast(list[int], roll["current_values"])[0])
        requests.append(payload)
        if not restored_once:
            checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
            restored = LocalGameSession.from_persistence_payload(checkpoint)
            assert restored.to_persistence_payload() == checkpoint
            for viewer in ("player-a", "player-b"):
                assert restored.view(viewer_player_id=viewer) == session.view(
                    viewer_player_id=viewer
                )
                assert restored.events_since(
                    EventStreamCursor(), viewer_player_id=viewer
                ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
            session = restored
            restored_once = True
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"{request.request_id}:order96",
            option_id=choice,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert attack_completed(session)
    assert len(requests) == 12
    assert values & {1, 2, 3}
    assert values & {4, 5, 6}
    wounds = attack_steps(session, "wound")
    assert len(wounds) == 12
    for wound in wounds:
        payload = cast(dict[str, JsonValue], wound["payload"])
        roll = cast(dict[str, JsonValue], payload["roll_state"])
        assert len(cast(list[JsonValue], roll["rerolls"])) == (choice != "decline")
    records = [
        record
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_dice_reroll"
    ]
    assert len(records) == 12
    assert all(record.result.selected_option_id == choice for record in records)
    assert not any(
        event.event_type == "weapon_ability_reroll_resolved"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    assert (
        LocalGameSession.from_persistence_payload(checkpoint).to_persistence_payload() == checkpoint
    )
    artifact = ReplayArtifact.capture(
        artifact_id="order96", initial_lifecycle_payload=initial, final_lifecycle=session.lifecycle
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize(
    "fault", ["duplicate_source", "duplicate_derived", "missing_source", "missing_derived", "drift"]
)
def test_d3_resume_rejects_incomplete_duplicate_or_changed_physical_evidence(fault: str) -> None:
    from warhammer40k_core.core.dice import D3RollResult, DiceRollResult
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.dice_roll_history import roll_or_reuse_d3
    from warhammer40k_core.engine.event_log import EventLog
    from warhammer40k_core.engine.phase import GameLifecycleError

    manager = DiceRollManager("order96-d3-authority")
    arguments = {
        "reason": "one physical critical hit",
        "roll_type": "sustained",
        "actor_id": "player-a",
    }
    original = roll_or_reuse_d3(manager=manager, **arguments)
    assert roll_or_reuse_d3(manager=manager, **arguments) == original
    assert len(manager.event_log.records) == 2
    log = EventLog()
    for event in manager.event_log.records:
        is_source = event.event_type == "dice_rolled"
        if (fault == "missing_source" and is_source) or (
            fault == "missing_derived" and not is_source
        ):
            continue
        payload = event.payload
        if fault == "drift" and not is_source:
            source = original.source_d6_result
            changed = DiceRollResult.from_values(
                roll_id=source.roll_id,
                spec=source.spec,
                values=(1 if source.values[0] != 1 else 6,),
                source="fixed",
            )
            payload = cast(JsonValue, D3RollResult.from_source_d6_result(changed).to_payload())
        log.append(event_type=event.event_type, payload=payload)
        if (fault == "duplicate_source" and is_source) or (
            fault == "duplicate_derived" and not is_source
        ):
            log.append(event_type=event.event_type, payload=payload)
    reconstructed = DiceRollManager("order96-d3-authority", event_log=log)
    with pytest.raises(GameLifecycleError, match="exactly one matching physical/derived pair"):
        roll_or_reuse_d3(manager=reconstructed, **arguments)


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("use_command", [False, True])
def test_twin_linked_decline_preserves_command_reroll_and_once_per_die(
    phase: BattlePhase, use_command: bool
) -> None:
    session = strength_session(phase, command_reroll=True)
    request = reach_wound_reroll(session)
    payload = cast(dict[str, JsonValue], request.payload)
    roll_id = payload["roll_id"]
    initial = session.lifecycle.to_payload()
    assert session.lifecycle.state is not None
    initial_cp = session.lifecycle.state.command_point_total("player-a")
    submit_next(session, request, reroll=not use_command)
    if use_command:
        command = pending_request(session)
        assert command.decision_type == "use_stratagem"
        option = next(o for o in command.options if o.option_id.startswith("use-stratagem:"))
        status = session.submit_option(
            request_id=command.request_id, option_id=option.option_id, result_id="order96:command"
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.command_point_total("player-a") == initial_cp - int(use_command)
    complete_optional_attack(session)
    records = [
        record
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_dice_reroll"
        and isinstance(record.request.payload, dict)
        and record.request.payload["roll_id"] == roll_id
    ]
    assert len(records) == 1
    rerolls = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "dice_reroll_resolved"
        and isinstance(event.payload, dict)
        and cast(dict[str, JsonValue], event.payload["original_result"])["roll_id"] == roll_id
    ]
    assert len(rerolls) == 1
    assert len(cast(list[JsonValue], rerolls[0]["rerolls"])) == 1
    state = session.lifecycle.state
    assert state is not None
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order96-command",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize(
    "field",
    [
        "game_id",
        "battle_round",
        "phase",
        "unit_instance_id",
        "attack_context_id",
        "weapon_profile_id",
        "source_payload",
        "wound_roll_state",
    ],
)
def test_twin_linked_pending_context_drift_is_atomic_and_restore_rejects(field: str) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = strength_session(BattlePhase.SHOOTING)
    request = reach_wound_reroll(session)
    payload = cast(dict[str, JsonValue], request.payload)
    context = cast(dict[str, JsonValue], payload["attack_context"])
    context[field] = "drifted"
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="order96:invalid", option_id="reroll:0"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    with pytest.raises(GameLifecycleError, match=r"[Ww]ound reroll"):
        GameLifecycle.from_payload(before)


@pytest.mark.parametrize("shooting", [False, True])
@pytest.mark.parametrize("choice", ["decline", "reroll:0"])
def test_retained_attacks_offer_owner_rerolls_and_resume_cleanup(
    shooting: bool, choice: str
) -> None:
    from tests.twin_linked_helpers import retained_twin_session

    session, model_id = retained_twin_session(shooting=shooting)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    offered = False
    for _ in range(100):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if offered and model_id in state.battlefield_state.removed_model_ids:
            break
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            status = session.submit_option(
                request_id=request.request_id,
                result_id="order96:retain",
                option_id="order96-retained",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif request.decision_type == "select_dice_reroll" and request.actor_id == "player-b":
            offered = True
            checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
            restored = LocalGameSession.from_persistence_payload(checkpoint)
            assert restored.to_persistence_payload() == checkpoint
            for viewer in ("player-a", "player-b"):
                assert restored.view(viewer_player_id=viewer) == session.view(
                    viewer_player_id=viewer
                )
            session = restored
            status = session.submit_option(
                request_id=request.request_id, result_id="order96:retained-reroll", option_id=choice
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif (
            request.decision_type == "submit_shooting_declaration"
            and request.actor_id == "player-b"
        ):
            from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

            from warhammer40k_core.engine.event_log import validate_json_value

            proposal = _proposal_from_request(
                request=request, target_unit_id="army-alpha:intercessor-1"
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="order96:retained-declaration",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        else:
            submit_next(session, request, reroll=True)
    assert offered
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order96-retained",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("reroll", [False, True])
def test_overlapping_wound_sources_offer_one_optional_choice(
    phase: BattlePhase, reroll: bool
) -> None:
    from dataclasses import replace

    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.effects import EffectExpiration

    session = strength_session(phase)
    state = session.lifecycle.state
    assert state is not None
    effect = generic_effect(
        effect_id="order96-overlap",
        owner_player_id="player-a",
        target_unit_instance_ids=("army-alpha:intercessor-1",),
        target_kind="this_unit",
        effect_kind="reroll_permission",
        parameters={"roll_type": "wound", "attack_role": "attacker"},
    )
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=phase,
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=phase, player_id="player-a"
            ),
        )
    )
    request = reach_wound_reroll(session)
    assert isinstance(request.payload, dict)
    assert request.payload["source_rule_id"] != TWIN_LINKED_RULE_ID
    complete_optional_attack(session, reroll=reroll)
    records = [
        record
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_dice_reroll"
    ]
    assert len(records) == 12
    assert (
        len({cast(str, cast(dict[str, JsonValue], r.request.payload)["roll_id"]) for r in records})
        == 12
    )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize(
    "field", ["request_id", "actor_id", "decision_type", "selected_option_id", "payload"]
)
def test_wound_reroll_malformed_results_do_not_consume_the_pending_choice(
    phase: BattlePhase, field: str
) -> None:
    from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload

    session = strength_session(phase)
    request = reach_wound_reroll(session)
    result = DecisionResult.for_request(
        request=request, selected_option_id="reroll:0", result_id="order96:invalid-result"
    )
    result_payload = cast(dict[str, JsonValue], result.to_payload())
    result_payload[field] = {"selected_indices": [1]} if field == "payload" else "stale"
    result = DecisionResult.from_payload(cast(DecisionResultPayload, result_payload))
    before = session.lifecycle.to_payload()
    status = session.lifecycle.submit_decision(result)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize(
    "field",
    [
        "roll_id",
        "roll_type",
        "source_rule_id",
        "permission",
        "current_values",
        "allowed_selections",
    ],
)
def test_wound_reroll_request_envelope_drift_is_atomic(field: str) -> None:
    session = strength_session(BattlePhase.SHOOTING)
    request = reach_wound_reroll(session)
    payload = cast(dict[str, JsonValue], request.payload)
    payload[field] = "attack_sequence.hit" if field == "roll_type" else "drifted"
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id="reroll:0", result_id="order96:envelope-drift"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("reaction", [False, True])
@pytest.mark.parametrize("reroll", [False, True])
def test_out_of_phase_twin_linked_resumes_its_shooting_host_from_movement(
    reaction: bool,
    reroll: bool,
) -> None:
    from tests.twin_linked_helpers import start_twin_overwatch

    session = strength_session(BattlePhase.SHOOTING)
    start_twin_overwatch(session, reaction=reaction)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    request = reach_wound_reroll(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.active_player_id == "player-b"
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert cast(dict[str, JsonValue], request.payload["attack_context"])["phase"] == "shooting"
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    complete_optional_attack(restored, reroll=reroll)
    assert attack_completed(restored)
    assert not restored.lifecycle.reaction_queue.frames
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order96-overwatch",
            initial_lifecycle_payload=initial,
            final_lifecycle=restored.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_wound_reroll_cannot_erase_its_attack_routing_identity() -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = strength_session(BattlePhase.SHOOTING)
    request = reach_wound_reroll(session)
    assert isinstance(request.payload, dict)
    request.payload.pop("attack_context")
    request.payload["roll_type"] = "advance"
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="order96:erased-route", option_id="reroll:0"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    with pytest.raises(GameLifecycleError, match=r"[Ww]ound reroll"):
        GameLifecycle.from_payload(before)


def test_restore_cannot_reclassify_a_physical_wound_in_both_pending_and_issued_requests() -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = strength_session(BattlePhase.SHOOTING)
    request = reach_wound_reroll(session)
    checkpoint = session.lifecycle.to_payload()
    pending = checkpoint["decisions"]["queue"]["pending_requests"][0]
    issued = next(
        e["payload"]
        for e in checkpoint["decisions"]["event_log"]
        if e["event_type"] == "decision_requested"
        and isinstance(e["payload"], dict)
        and e["payload"]["request_id"] == request.request_id
    )
    for row in (pending, issued):
        payload = cast(dict[str, JsonValue], row["payload"])
        payload.pop("attack_context")
        payload["roll_type"] = "advance"
    with pytest.raises(GameLifecycleError, match=r"[Ww]ound reroll"):
        GameLifecycle.from_payload(checkpoint)


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("reroll", [False, True])
def test_sustained_d3_is_stable_across_twin_linked_resume_restore_and_replay(
    phase: BattlePhase,
    reroll: bool,
) -> None:
    from tests.twin_linked_helpers import sustained_twin_session

    session = sustained_twin_session(phase)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    restored = False
    for _ in range(150):
        if attack_completed(session):
            break
        request = pending_request(session)
        if (
            request.decision_type == "select_dice_reroll"
            and not restored
            and any(
                event.event_type == "d3_roll_resolved"
                for event in session.lifecycle.decision_controller.event_log.records
            )
        ):
            checkpoint = session.to_persistence_payload()
            session = LocalGameSession.from_persistence_payload(checkpoint)
            assert session.to_persistence_payload() == checkpoint
            restored = True
        submit_next(session, request, reroll=reroll)
    assert attack_completed(session)
    assert restored
    hits = attack_steps(session, "hit")
    assert len({cast(str, row["attack_context_id"]) for row in hits}) == len(hits)
    critical = [row for row in hits if cast(dict[str, JsonValue], row["payload"])["critical"]]
    physical = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and cast(dict[str, JsonValue], event.payload["spec"])["roll_type"]
        == "attack_sequence.sustained_hits.generated_hits.d3_source"
    ]
    assert len(physical) == len(critical) > 0
    assert len(
        {cast(str, cast(dict[str, JsonValue], p["spec"])["reason"]) for p in physical}
    ) == len(physical)
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order96-sustained",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("reroll", [False, True])
def test_twin_linked_continues_real_fight_interrupt_frame_until_parent_resumes(
    reroll: bool,
) -> None:
    from tests.twin_linked_helpers import interrupt_twin_session

    session = interrupt_twin_session()
    pending_request(session)
    initial = session.lifecycle.to_payload()
    choices = 0
    for _ in range(60):
        if choices and not session.lifecycle.reaction_queue.frames:
            break
        request = pending_request(session)
        if request.decision_type == "resolve_fight_interrupt":
            option_id = next(
                option.option_id for option in request.options if "decline" not in option.option_id
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option_id,
                result_id="order96:real-interrupt",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        elif (
            request.decision_type == "select_dice_reroll"
            and session.lifecycle.reaction_queue.frames
        ):
            choices += 1
            assert request.actor_id == "player-b"
            submit_next(session, request, reroll=reroll)
            frames = session.lifecycle.reaction_queue.frames
            if frames:
                assert frames[-1].request_id == pending_request(session).request_id
            session = session.fork()
        else:
            submit_next(session, request)
    assert choices == 2
    assert not session.lifecycle.reaction_queue.frames
    assert any(
        e.event_type == "reaction_parent_resumed"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order96-interrupt",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
