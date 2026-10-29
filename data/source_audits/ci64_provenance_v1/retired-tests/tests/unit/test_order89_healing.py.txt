from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.order89_healing_helpers import healing_scene

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.healing import (
    HealingStepKind,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("actor", [None, "player-b"])
def test_any_unit_offers_wounded_model_choice_to_source_actor(
    attached: bool,
    actor: str | None,
) -> None:
    lifecycle, effect, ids, _ = healing_scene(wounded=(0, 1), attached=attached)
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=replace(effect, selection_actor_player_id=actor),
    )
    assert request is not None
    assert request.actor_id == (actor or "player-a")
    assert len(request.options) == 2
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    session = LocalGameSession.from_persistence_payload(checkpoint)
    for viewer in ("player-a", "player-b"):
        json.dumps(session.view(viewer_player_id=viewer))
    before = session.lifecycle.to_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=request.request_id, option_id="invented-option", result_id="order89-invalid"
        )
    assert session.lifecycle.to_payload() == before
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order89-select",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert session.lifecycle.state is not None
    healed = [
        model_by_id(state=session.lifecycle.state, model_instance_id=i).current_wounds
        for i in ids[:2]
    ]
    assert sorted(healed) == [1, 2]
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order89")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("explicit", [False, True])
def test_character_exclusion_is_only_for_ordinary_unit_healing(explicit: bool) -> None:
    lifecycle, effect, ids, _ = healing_scene(destroyed=(5,), attached=True)
    state = lifecycle.state
    assert state is not None
    if explicit:
        effect = replace(
            effect,
            source_context={"revive_destroyed_models_only": True, "revive_model_full_health": True},
        )
    resolved, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    if explicit:
        assert request is not None
        assert request.decision_type == "submit_healing_revival_placement"
    else:
        assert request is None
        assert resolved.resolved_steps[0].step_kind is HealingStepKind.NO_EFFECT
    assert model_by_id(state=state, model_instance_id=ids[5]).current_wounds == 0


def test_model_healing_discards_excess_without_healing_another_model_or_reviving() -> None:
    lifecycle, effect, ids, _ = healing_scene(wounded=(0, 1), destroyed=(2,), amount=5)
    state = lifecycle.state
    assert state is not None
    resolved, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=replace(effect, source_context={"healing_model_instance_id": ids[1]}),
    )
    assert request is None
    assert resolved.is_complete()
    assert [model_by_id(state=state, model_instance_id=i).current_wounds for i in ids[:3]] == [
        1,
        2,
        0,
    ]


@pytest.mark.parametrize("explicit", [False, True])
def test_mixed_attached_revival_candidates_and_accepted_placement_replay(explicit: bool) -> None:
    from tests.order83_revival_helpers import revival_proposal

    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    lifecycle, effect, ids, placements = healing_scene(destroyed=(0, 5), attached=True)
    state = lifecycle.state
    assert state is not None
    if explicit:
        effect = replace(
            effect,
            source_context={"revive_destroyed_models_only": True, "revive_model_full_health": True},
        )
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    chosen = ids[5] if explicit else ids[0]
    if explicit:
        assert len(request.options) == 2
        option = next(
            o
            for o in request.options
            if isinstance(o.payload, dict) and o.payload["model_instance_id"] == chosen
        )
        status = restored.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id="order89-return-choice",
        )
        request = status.decision_request
        assert request is not None
    assert request.decision_type == "submit_healing_revival_placement"
    placement = placements[chosen]
    status = restored.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order89-return-placement",
        payload=revival_proposal(request, placement, placement.pose),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert restored.lifecycle.state is not None
    model = model_by_id(state=restored.lifecycle.state, model_instance_id=chosen)
    assert model.current_wounds == (model.initial_wounds if explicit else 1)
    assert (
        model_by_id(
            state=restored.lifecycle.state, model_instance_id=ids[0] if explicit else ids[5]
        ).current_wounds
        == 0
    )
    for viewer in ("player-a", "player-b"):
        delta = restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert any(event["event_type"] == "healing_step_resolved" for event in delta["events"])
    assert (
        ReplayRunner.from_payload(restored.replay_artifact(artifact_id="order89-revival"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "source",
    [
        {"single_model_heal": True},
        {"heal_wounded_models_only": True, "single_model_heal": True},
    ],
)
def test_selected_model_heal_locks_after_choice_and_discards_excess(
    source: dict[str, bool],
) -> None:
    from warhammer40k_core.engine.event_log import validate_json_value

    lifecycle, effect, ids, _ = healing_scene(wounded=(0, 1), destroyed=(2,), amount=5)
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=replace(effect, source_context=validate_json_value(source)),
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[1].option_id,
        result_id="order89-one-model",
    )
    assert [model_by_id(state=state, model_instance_id=i).current_wounds for i in ids[:3]] == [
        1,
        2,
        0,
    ]
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order89-one-model"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "source",
    [
        {"single_model_heal": True, "revive_destroyed_models_only": True},
        {"revive_model_full_health": True},
        {"healing_model_instance_id": ""},
        {"healing_model_instance_id": 42},
        {"single_model_heal": "yes"},
        {"healing_model_instance_id": "model-id", "single_model_heal": "yes"},
        {"healing_model_instance_id": "model-id", "heal_wounded_models_only": "yes"},
        {"single_model_heal": True, "heal_wounded_models_only": "yes"},
    ],
)
def test_invalid_healing_scope_fails_before_mutation(source: object) -> None:
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, effect, _, _ = healing_scene()
    before = lifecycle.to_payload()
    with pytest.raises(GameLifecycleError):
        replace(effect, source_context=validate_json_value(source))
    assert lifecycle.to_payload() == before


def test_healing_model_identity_must_belong_to_target_and_dead_models_are_not_revived() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, effect, ids, _ = healing_scene(wounded=(0,), destroyed=(1,), amount=3)
    state = lifecycle.state
    assert state is not None
    before = lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="belong"):
        resolve_healing_until_blocked(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            effect=replace(effect, source_context={"healing_model_instance_id": "unknown"}),
        )
    assert lifecycle.to_payload() == before
    for target in (ids[1], ids[2]):
        resolved, request = resolve_healing_until_blocked(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            effect=replace(
                effect,
                effect_id=f"heal:{target}",
                source_context={"healing_model_instance_id": target},
            ),
        )
        assert request is None
        assert all(step.step_kind is HealingStepKind.NO_EFFECT for step in resolved.resolved_steps)
    assert model_by_id(state=state, model_instance_id=ids[0]).current_wounds == 1


@pytest.mark.parametrize(("field", "value"), [("actor_id", "player-b"), ("option_label", "Forged")])
def test_restored_healing_request_must_match_engine_candidates_and_actor(
    field: str, value: str
) -> None:
    from typing import cast

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, effect, _, _ = healing_scene(wounded=(0, 1))
    state = lifecycle.state
    assert state is not None
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    payload = json.loads(json.dumps(lifecycle.to_payload()))

    def forge(value_to_change: JsonValue) -> None:
        if isinstance(value_to_change, dict):
            if (
                value_to_change.get("request_id") == request.request_id
                and "options" in value_to_change
            ):
                if field == "actor_id":
                    value_to_change["actor_id"] = value
                else:
                    options = cast(list[dict[str, JsonValue]], value_to_change["options"])
                    options[0]["label"] = value
            for child in value_to_change.values():
                forge(child)
        elif isinstance(value_to_change, list):
            for child in value_to_change:
                forge(child)

    forge(payload)
    with pytest.raises(GameLifecycleError, match="Pending healing selection drifted"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))
