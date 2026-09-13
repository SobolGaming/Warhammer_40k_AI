"""Order 44: each critical Lethal Hit has a canonical player choice."""

from __future__ import annotations

import pytest
from tests.lethal_hits_helpers import (
    attack_steps,
    complete_attack,
    lethal_session,
    reach_lethal_choice,
)

from warhammer40k_core.engine.phase import BattlePhase


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_lethal_hit_offers_both_choices_before_wounding(phase: BattlePhase) -> None:
    session = lethal_session(phase)
    request = reach_lethal_choice(session)
    assert request.actor_id == "player-a"
    assert tuple(option.option_id for option in request.options) == ("auto-wound", "roll-to-wound")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("choice", ["auto-wound", "roll-to-wound"])
def test_choices_devastating_sustained_restore_and_replay(phase: BattlePhase, choice: str) -> None:
    from typing import cast

    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import JsonValue, canonical_json
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    session = lethal_session(phase, devastating=True)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    request = reach_lethal_choice(session)
    payload = cast(dict[str, JsonValue], request.payload)
    attack_id = payload["attack_context_id"]
    assert not any(row["attack_context_id"] == attack_id for row in attack_steps(session, "wound"))
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    # Fixed legal result identities exercise an original critical wound in each
    # phase without replacing RNG or the engine's decision controller.
    first_result_id = f"order44:first-choice-{0 if phase is BattlePhase.SHOOTING else 1}"
    for current in (session, restored):
        current.submit_option(
            request_id=request.request_id, result_id=first_result_id, option_id=choice
        )
    complete_attack(session, choice=choice)
    complete_attack(restored, choice=choice)
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    choices = [
        record
        for record in session.lifecycle.decision_controller.records
        if record.request.decision_type == "select_lethal_hit_wound"
    ]
    critical_hits = attack_steps(session, "critical_hit")
    assert len(choices) == len(critical_hits) > 0
    choice_attacks = {
        cast(str, cast(dict[str, JsonValue], record.request.payload)["attack_context_id"])
        for record in choices
    }
    wounds = attack_steps(session, "wound")
    assert wounds
    generated: list[dict[str, JsonValue]] = []
    for wound in wounds:
        rolled = cast(dict[str, JsonValue], wound["payload"])
        if wound["attack_context_id"] in choice_attacks:
            assert rolled["skipped"] is (choice == "auto-wound")
            if choice == "auto-wound":
                assert rolled["successful"]
                assert not rolled["critical"]
                assert rolled["roll_state"] is None
        elif ":generated-hit-" in cast(str, wound["attack_context_id"]):
            generated.append(wound)
            assert not rolled["skipped"]
    assert len(generated) == len(critical_hits)
    if choice == "roll-to-wound":
        # Strength 1 only wounds this target on a six, so every successful
        # declined original attack is critical and invokes Devastating Wounds.
        assert any(
            wound["attack_context_id"] in choice_attacks
            and cast(dict[str, JsonValue], wound["payload"])["critical"] is True
            for wound in wounds
        )
        assert any(
            event.event_type == "devastating_wounds_deferred"
            and isinstance(event.payload, dict)
            and event.payload["attack_context_id"] in choice_attacks
            for event in session.lifecycle.decision_controller.event_log.records
        )
    serialized = canonical_json([record.to_payload() for record in choices])
    assert "0x" not in serialized
    assert "gw-11e-core-lethal-hits:lethal-hits" in serialized
    artifact = ReplayArtifact.capture(
        artifact_id="order44", initial_lifecycle_payload=initial, final_lifecycle=session.lifecycle
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    for viewer in ("player-a", "player-b"):
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize(
    "field", ["request_id", "actor_id", "decision_type", "selected_option_id", "payload"]
)
def test_invalid_results_preserve_pending_request_and_state(phase: BattlePhase, field: str) -> None:
    from typing import cast

    from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = lethal_session(phase)
    request = reach_lethal_choice(session)
    result = DecisionResult.for_request(
        result_id="order44:invalid", request=request, selected_option_id="auto-wound"
    )
    payload = cast(dict[str, JsonValue], result.to_payload())
    payload[field] = {"choice": "roll-to-wound"} if field == "payload" else "stale"
    changed = DecisionResult.from_payload(cast(DecisionResultPayload, payload))
    before = session.lifecycle.to_payload()
    status = session.lifecycle.submit_decision(changed)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize(
    "field",
    [
        "source_rule_id",
        "sequence_id",
        "attack_index",
        "generated_hit_index",
        "target_unit_instance_id",
        "weapon_profile_id",
        "weapon_profile",
        "target_keywords",
        "selected_weapon_ability_ids",
        "option",
    ],
)
def test_request_drift_rejected_on_restore_and_before_queue_pop(
    phase: BattlePhase, field: str
) -> None:
    from typing import cast

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind

    session = lethal_session(phase)
    request = reach_lethal_choice(session)
    payload = cast(dict[str, JsonValue], request.payload)
    if field == "option":
        cast(dict[str, JsonValue], request.options[0].payload)["choice"] = "roll-to-wound"
    elif field in ("attack_index", "generated_hit_index"):
        payload[field] = 99
    elif field in ("target_keywords", "selected_weapon_ability_ids"):
        payload[field] = ["INVENTED"]
    elif field == "weapon_profile":
        cast(dict[str, JsonValue], payload[field])["profile_id"] = "invented:weapon"
    else:
        payload[field] = "invented:identity"
    before = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match=r"Lethal Hits|Hit authority"):
        GameLifecycle.from_payload(before)
    status = session.submit_option(
        request_id=request.request_id, result_id="order44:drifted", option_id="auto-wound"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("mode", ["torrent", "wrong-target"])
def test_noneligible_hits_have_no_lethal_choice(phase: BattlePhase, mode: str) -> None:
    session = lethal_session(
        phase,
        torrent=mode == "torrent",
        target_keywords=("TITANIC",) if mode == "wrong-target" else (),
    )
    complete_attack(session)
    assert not any(
        record.request.decision_type == "select_lethal_hit_wound"
        for record in session.lifecycle.decision_controller.records
    )


def test_out_of_phase_snap_shooting_choice_uses_attacking_owner_and_replays() -> None:
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.command_points import CommandPointSourceKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.stratagem_catalog import (
        eleventh_edition_stratagem_catalog_records,
    )
    from warhammer40k_core.engine.stratagems import (
        FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY,
        StratagemEligibilityContext,
        StratagemTargetBinding,
        StratagemTargetKind,
        StratagemTargetProposal,
        request_stratagem_target_proposal,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    session = lethal_session(BattlePhase.SHOOTING)
    state = session.lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="order44:cp",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    record = next(
        row
        for row in eleventh_edition_stratagem_catalog_records()
        if row.definition.stratagem_id == "fire-overwatch"
    )
    proposal = StratagemTargetProposal.for_request(
        context=StratagemEligibilityContext.from_state(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.END_PHASE,
            trigger_payload={
                FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY: "army-beta:enemy",
                "movement_phase_action": "normal_move",
                "movement_payload": {
                    "unit_instance_id": "army-beta:enemy",
                    "movement_phase_action": "normal_move",
                },
            },
        ),
        catalog_record=record,
    )
    status = request_stratagem_target_proposal(
        state=state,
        decisions=session.lifecycle.decision_controller,
        proposal_request=proposal,
    )
    assert status.decision_request is not None
    request = status.decision_request
    proposal = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-1",
        )
    )
    assert session.advance_until_decision_or_terminal().decision_request == request
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order44:overwatch-result",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    assert status.decision_request is not None, status
    assert status.decision_request.decision_type == "submit_shooting_declaration", status
    initial = session.lifecycle.to_payload()
    # This fixed accepted declaration identity gives an unmodified six in Snap
    # Shooting; the original fixture identity misses with all eighteen attacks.
    session.submit_parameterized_payload(
        request_id=status.decision_request.request_id,
        result_id="order44:overwatch-declaration",
        payload=validate_json_value(
            _proposal_from_request(
                request=status.decision_request, target_unit_id="army-beta:enemy"
            ).to_payload()
        ),
    )
    request = reach_lethal_choice(session)
    assert request.actor_id == "player-a"
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    complete_attack(session, choice="roll-to-wound")
    complete_attack(restored, choice="roll-to-wound")
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    artifact = ReplayArtifact.capture(
        artifact_id="order44:overwatch",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize(
    "forgery", ["missing-choice", "changed-wound", "changed-choice", "duplicate-choice"]
)
def test_restored_wounds_require_the_recorded_choice(phase: BattlePhase, forgery: str) -> None:
    from copy import deepcopy
    from typing import cast

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = lethal_session(phase)
    complete_attack(session)
    payload = deepcopy(session.lifecycle.to_payload())
    controller = payload["decisions"]
    records = controller["records"]
    record = next(r for r in records if r["request"]["decision_type"] == "select_lethal_hit_wound")
    if forgery == "changed-wound":
        request = cast(dict[str, JsonValue], record["request"]["payload"])
        event = next(
            e
            for e in controller["event_log"]
            if e["event_type"] == "attack_sequence_step"
            and isinstance(e["payload"], dict)
            and e["payload"].get("step") == "wound"
            and e["payload"].get("attack_context_id") == request["attack_context_id"]
        )
        cast(dict[str, JsonValue], cast(dict[str, JsonValue], event["payload"])["payload"])[
            "skipped"
        ] = False
    elif forgery == "missing-choice":
        records.remove(record)
        for index, row in enumerate(records, 1):
            row["record_id"] = f"decision-record-{index:06d}"
    elif forgery == "changed-choice":
        record["result"]["selected_option_id"] = "roll-to-wound"
        record["result"]["payload"] = {"choice": "roll-to-wound"}
    else:
        duplicate = deepcopy(record)
        duplicate["record_id"] = f"decision-record-{len(records) + 1:06d}"
        records.append(duplicate)
    with pytest.raises(GameLifecycleError, match="Lethal Hits"):
        GameLifecycle.from_payload(payload)


def test_lethal_hits_source_is_pinned_and_executable() -> None:
    from importlib.resources import files

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_lethal_hits_2026_09 as source,
    )

    raw = files(source).joinpath("artifacts/package.json").read_bytes()
    artifact = source.validate_source_artifact_bytes(raw)
    assert source.source_package().source_catalog.catalog_sha256()
    assert source.source_evidence_records()
    assert artifact.rules == source.source_rules()
    assert artifact.rules[0].source_id == source.LETHAL_HITS_SOURCE_ID
    assert artifact.rules[0].load_support_status == "loaded"
    assert artifact.rules[0].semantic_execution_status == "executable_engine_runtime"
    with pytest.raises(source.LethalHitsSourceError, match="drifted"):
        source.validate_source_artifact_bytes(raw + b" ")


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_r44_001_declined_wound_checkpoint_continues_without_drift(phase: BattlePhase) -> None:
    from tests.lethal_hits_helpers import lethal_wound_checkpoint
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = lethal_wound_checkpoint(phase=phase)
    saved = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    for current in (session, restored):
        request = pending_request(current)
        status = current.submit_option(
            request_id=request.request_id,
            result_id="r44:continue-wound",
            option_id="decline_stratagem_window",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        complete_attack(current, choice="roll-to-wound")
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    completed = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(completed).to_payload() == completed


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("checkpoint", ["wound-reroll", "completed"])
@pytest.mark.parametrize(
    "forgery",
    [
        "missing-choice",
        "target",
        "target-keywords",
        "mirrored-target",
        "missing-recorded",
        "orphan-issued",
        "missing-issued",
        "duplicate-issued",
        "duplicate-recorded",
        "answer-before-request",
        "request-before-hit",
    ],
)
def test_r44_001_historical_choices_are_authenticated_before_restore(
    phase: BattlePhase,
    checkpoint: str,
    forgery: str,
) -> None:
    from copy import deepcopy
    from typing import cast

    from tests.lethal_hits_helpers import lethal_wound_checkpoint

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = lethal_wound_checkpoint(phase=phase)
    if checkpoint == "completed":
        complete_attack(session, choice="roll-to-wound")
    payload = deepcopy(session.lifecycle.to_payload())
    records = payload["decisions"]["records"]
    events = payload["decisions"]["event_log"]
    choice = next(r for r in records if r["request"]["decision_type"] == "select_lethal_hit_wound")
    issued = next(
        e
        for e in events
        if e["event_type"] == "decision_requested" and e["payload"] == choice["request"]
    )
    recorded = next(
        e for e in events if e["event_type"] == "decision_recorded" and e["payload"] == choice
    )
    if forgery in ("missing-choice", "orphan-issued"):
        records.remove(choice)
        if forgery == "orphan-issued":
            events.remove(recorded)
    elif forgery == "target-keywords":
        cast(dict[str, JsonValue], choice["request"]["payload"])["target_keywords"] = ["INVENTED"]
    elif forgery in ("target", "mirrored-target"):
        cast(dict[str, JsonValue], choice["request"]["payload"])["target_unit_instance_id"] = (
            "invented-target"
        )
        if forgery == "mirrored-target":
            # Agreement between the record and its decision_recorded copy is
            # insufficient: the issued request remains the original authority.
            recorded["payload"] = cast(JsonValue, deepcopy(choice))
    elif forgery == "missing-recorded":
        events.remove(recorded)
    elif forgery == "missing-issued":
        events.remove(issued)
    elif forgery in ("duplicate-issued", "duplicate-recorded"):
        events.append(deepcopy(issued if forgery == "duplicate-issued" else recorded))
    elif forgery == "answer-before-request":
        issued_index, recorded_index = events.index(issued), events.index(recorded)
        events[issued_index], events[recorded_index] = recorded, issued
    else:
        attack_id = cast(dict[str, JsonValue], choice["request"]["payload"])["attack_context_id"]
        hit = next(
            e
            for e in events
            if e["event_type"] == "attack_sequence_step"
            and isinstance(e["payload"], dict)
            and e["payload"].get("step") == "hit"
            and e["payload"].get("attack_context_id") == attack_id
        )
        events.remove(issued)
        events.insert(events.index(hit), issued)
    for index, record in enumerate(records, 1):
        record["record_id"] = f"decision-record-{index:06d}"
    for index, event in enumerate(events, 1):
        event["event_id"] = f"event-{index:06d}"
    before = deepcopy(payload)
    with pytest.raises(GameLifecycleError, match="Lethal Hits"):
        GameLifecycle.from_payload(payload)
    assert payload == before


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_r44_001_wound_cannot_precede_its_recorded_answer(phase: BattlePhase) -> None:
    from copy import deepcopy
    from typing import cast

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = lethal_session(phase)
    complete_attack(session, choice="roll-to-wound")
    payload = deepcopy(session.lifecycle.to_payload())
    choice = next(
        r
        for r in payload["decisions"]["records"]
        if r["request"]["decision_type"] == "select_lethal_hit_wound"
    )
    attack_id = cast(dict[str, JsonValue], choice["request"]["payload"])["attack_context_id"]
    events = payload["decisions"]["event_log"]
    recorded = next(
        e for e in events if e["event_type"] == "decision_recorded" and e["payload"] == choice
    )
    wound = next(
        e
        for e in events
        if e["event_type"] == "attack_sequence_step"
        and isinstance(e["payload"], dict)
        and e["payload"].get("step") == "wound"
        and e["payload"].get("attack_context_id") == attack_id
    )
    events.remove(recorded)
    events.insert(events.index(wound) + 1, recorded)
    for index, event in enumerate(events, 1):
        event["event_id"] = f"event-{index:06d}"
    with pytest.raises(GameLifecycleError, match="Lethal Hits wound precedes"):
        GameLifecycle.from_payload(payload)
