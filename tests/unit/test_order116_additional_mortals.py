from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.lethal_hits_helpers import attack_completed, complete_attack
from tests.order116_mortal_helpers import SOURCE_ID, additional_mortal_session
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.additional_attack_mortal_permissions import (
    additional_attack_mortal_permission_effect,
    validate_additional_attack_mortal_permission,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_source_backed_additional_mortals_preserve_attack_identity_and_damage_order(
    phase: BattlePhase,
) -> None:
    session = additional_mortal_session(phase)
    complete_attack(session)
    events = session.lifecycle.decision_controller.event_log.records
    deferred = [e for e in events if e.event_type == "additional_attack_mortal_wounds_deferred"]
    resolved = [e for e in events if e.event_type == "additional_attack_mortal_wounds_applied"]
    assert deferred
    assert len(resolved) == len(deferred)
    normal = [
        e
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "damage"
        and isinstance(e.payload.get("payload"), dict)
        and cast(dict[str, JsonValue], e.payload["payload"]).get("damage_application") is not None
    ]
    assert normal
    assert max(events.index(e) for e in normal) < min(events.index(e) for e in resolved)
    assert all(
        cast(dict[str, JsonValue], e.payload)["source_rule_id"] == SOURCE_ID for e in resolved
    )
    assert [cast(dict[str, JsonValue], e.payload)["attack_context_ids"] for e in resolved] == [
        [cast(dict[str, JsonValue], e.payload)["attack_context_id"]] for e in deferred
    ]
    assert any(
        cast(
            dict[str, JsonValue], cast(dict[str, JsonValue], e.payload)["mortal_wound_application"]
        )["applications"]
        for e in resolved
    )
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="order116-complete")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_additional_mortal_pending_retry_restore_and_lethal_continuation(
    phase: BattlePhase,
) -> None:
    session = additional_mortal_session(phase, mortal_wounds=8, optional_fnp=True)
    reached = False
    for _ in range(100):
        if attack_completed(session):
            break
        request = pending_request(session)
        if request.decision_type in {
            "select_feel_no_pain",
            "select_mortal_wound_model",
        } and isinstance(request.payload, dict):
            context = request.payload.get("lost_wound_context") or request.payload.get(
                "mortal_wound_context"
            )
            if (
                isinstance(context, dict)
                and isinstance(context.get("source_context"), dict)
                and cast(dict[str, JsonValue], context["source_context"]).get("source_kind")
                == "additional_attack_mortal_wounds"
            ):
                reached = True
                checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
                session = LocalGameSession.from_persistence_payload(checkpoint)
                fork = LocalGameSession.from_persistence_payload(checkpoint)
                with pytest.raises(DecisionError, match="finite action space"):
                    session.submit_option(
                        request_id=request.request_id,
                        result_id=f"{request.request_id}:invalid",
                        option_id="absent-option",
                    )
                assert session.to_persistence_payload() == checkpoint
                submit_fixture_request(session, request)
                assert fork.to_persistence_payload() == checkpoint
                continue
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Additional mortal attack did not complete.")
    assert reached
    assert attack_completed(session)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order116-lethal")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_additional_mortal_weapon_scope_is_source_owned(phase: BattlePhase) -> None:
    session = additional_mortal_session(
        phase, scope="melee" if phase is BattlePhase.SHOOTING else "ranged"
    )
    complete_attack(session)
    assert not any(
        e.event_type == "additional_attack_mortal_wounds_deferred"
        for e in session.lifecycle.decision_controller.event_log.records
    )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_additional_mortal_permission_validates_schema_and_occurrence(phase: BattlePhase) -> None:
    session = additional_mortal_session(phase)
    state = session.lifecycle.state
    assert state is not None
    effect = next(
        e for e in state.persisting_effects if e.effect_id == "order116:source-permission"
    )
    assert isinstance(effect.effect_payload, dict)
    for change in (
        {"mortal_wounds": 0},
        {"mortal_wounds": True},
        {"weapon_scope": "invalid"},
        {"occasion_id": ""},
    ):
        with pytest.raises(GameLifecycleError, match="permission"):
            validate_additional_attack_mortal_permission(
                replace(effect, effect_payload={**effect.effect_payload, **change})
            )
    with pytest.raises(GameLifecycleError, match="schema drift"):
        additional_attack_mortal_permission_effect(
            state=state,
            effect_id="invalid",
            source_rule_id=SOURCE_ID,
            source_model_instance_id=cast(str, effect.effect_payload["source_model_instance_id"]),
            occasion_id="source-occasion",
            mortal_wounds=0,
            weapon_scope="all",
        )


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
def test_successful_wounds_generate_additional_mortals_even_after_successful_saves(
    phase: BattlePhase,
) -> None:
    session = additional_mortal_session(phase, armor_penetration=0)
    complete_attack(session)
    events = session.lifecycle.decision_controller.event_log.records
    wounded = [
        e
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "wound"
        and isinstance(e.payload.get("payload"), dict)
        and cast(dict[str, JsonValue], e.payload["payload"]).get("successful") is True
    ]
    failed = [
        e
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "wound"
        and isinstance(e.payload.get("payload"), dict)
        and cast(dict[str, JsonValue], e.payload["payload"]).get("successful") is False
    ]
    saved = [
        e
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "save"
        and isinstance(e.payload.get("payload"), dict)
        and cast(dict[str, JsonValue], e.payload["payload"]).get("successful") is True
    ]
    assert wounded
    assert saved
    deferred = [e for e in events if e.event_type == "additional_attack_mortal_wounds_deferred"]
    ids = {cast(str, cast(dict[str, JsonValue], e.payload)["attack_context_id"]) for e in deferred}
    assert ids == {
        cast(str, cast(dict[str, JsonValue], e.payload)["attack_context_id"]) for e in wounded
    }
    assert not ids.intersection(
        cast(dict[str, JsonValue], e.payload)["attack_context_id"] for e in failed
    )


def test_additional_mortals_coexist_with_native_devastating_wounds() -> None:
    session = additional_mortal_session(BattlePhase.SHOOTING, devastating=True, attacks=12)
    complete_attack(session)
    events = session.lifecycle.decision_controller.event_log.records
    extra = [e for e in events if e.event_type == "additional_attack_mortal_wounds_deferred"]
    native = [e for e in events if e.event_type == "devastating_wounds_mortal_wounds_applied"]
    assert extra
    assert native
    extra_contexts = {
        cast(str, cast(dict[str, JsonValue], e.payload)["attack_context_id"]) for e in extra
    }
    assert all(
        set(cast(list[str], cast(dict[str, JsonValue], e.payload)["attack_context_ids"]))
        <= extra_contexts
        for e in native
    )
    assert any(e.event_type == "additional_attack_mortal_wounds_applied" for e in events)
    assert (
        ReplayRunner.from_payload(
            session.replay_artifact(artifact_id="order116-devastating-coexist")
        )
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
