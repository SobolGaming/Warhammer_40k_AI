"""Gathered Psychic choices retain per-occurrence authority at every boundary.

These use the existing admitted Core facade fixture, including its constructed
phase and generic source effects; they do not certify a faction provider.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.psychic_modifier_helpers import (
    pending_request,
    psychic_session,
    reach_psychic_request,
    submit_fixture_request,
)

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponProfile
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    DecisionRequestPayload,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle_for_armies
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.psychic_modifier_validation import invalid_psychic_modifier_status
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


def _session(phase: BattlePhase, *, random_skill: bool = False) -> LocalGameSession:
    def profile(source: WeaponProfile) -> WeaponProfile:
        return replace(
            source,
            attack_profile=AttackProfile.fixed(3),
            skill=RandomProfileValue(
                source.skill.characteristic,
                DiceExpression(1, 3, 1),
                "fixture:order135:random-psychic-skill",
            )
            if random_skill
            else source.skill,
            source_ids=(*source.source_ids, "fixture:order135:random-psychic-skill")
            if random_skill
            else source.source_ids,
        )

    return psychic_session(phase, weapon_profile_transform=profile)


def _assert_checkpoint(session: LocalGameSession) -> tuple[LocalGameSession, LocalGameSession]:
    before = session.lifecycle.to_payload()
    persistence = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(persistence)
    forked = session.fork()
    assert restored.to_persistence_payload() == persistence
    for branch in (restored, forked):
        assert branch.lifecycle.to_payload() == before
        viewers = (
            ViewerContext.for_player("player-a"),
            ViewerContext.for_player("player-b"),
            ViewerContext(
                principal_id="psychic:coach",
                role=PrincipalRole.COACH,
                viewer_player_id="player-a",
                policy=ROLE_POLICY_BY_ROLE[PrincipalRole.COACH],
            ),
            *(
                ViewerContext(
                    principal_id=f"psychic:{role.value}",
                    role=role,
                    viewer_player_id=None,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                for role in (
                    PrincipalRole.DELAYED_SPECTATOR,
                    PrincipalRole.ADMINISTRATOR,
                    PrincipalRole.REPLAY_VIEWER,
                )
            ),
        )
        for viewer in viewers:
            assert branch.view_for_context(viewer=viewer) == session.view_for_context(viewer=viewer)
            assert branch.events_since_for_context(
                EventStreamCursor(), viewer=viewer
            ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
        assert branch.lifecycle.decision_controller.event_log.records == (
            session.lifecycle.decision_controller.event_log.records
        )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="gathered-psychic"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    assert session.lifecycle.to_payload() == before
    return restored, forked


def _context(request: DecisionRequest) -> str:
    assert isinstance(request.payload, dict)
    context = request.payload["attack_context_id"]
    assert isinstance(context, str)
    return context


def _hits(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    return [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "hit"
    ]


@pytest.mark.parametrize("phase", [BattlePhase.SHOOTING, BattlePhase.FIGHT])
@pytest.mark.parametrize("random_skill", [False, True])
def test_all_original_psychic_preparations_restore_fork_and_replay(
    phase: BattlePhase, random_skill: bool
) -> None:
    session = _session(phase, random_skill=random_skill)
    request = reach_psychic_request(session)
    state = session.lifecycle.state
    assert state is not None
    host = active_attack_sequence_for_state(state)
    assert host is not None
    assert host.attack_index == 0
    assert host.current_pool().attacks == 3
    contexts = tuple(replace(host, attack_index=i).attack_context_id() for i in range(3))
    for index, context in enumerate(contexts):
        assert _context(request) == context
        assert active_attack_sequence_for_state(state) == host
        assert not _hits(session)
        if index == 1:
            option = next(
                option
                for option in request.options
                if option.option_id.startswith("keep-modifier:")
            )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:partial",
                option_id=option.option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
            request = pending_request(session)
            assert _context(request) == context
        restored, forked = _assert_checkpoint(session)
        for branch in (session, restored, forked):
            status = branch.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:complete",
                option_id="keep-all-modifiers",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
        assert session.lifecycle.to_payload() == forked.lifecycle.to_payload()
        if index < 2:
            request = pending_request(session)
    for _ in range(40):
        if len(_hits(session)) == 3:
            break
        submit_fixture_request(session, pending_request(session))
    hits = _hits(session)
    assert [event["attack_context_id"] for event in hits] == list(contexts)
    assert all(
        isinstance(event["payload"], dict)
        and event["payload"]["psychic_modifier_selection"] is not None
        for event in hits
    )
    _assert_checkpoint(session)
    if random_skill:
        evaluations = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "random_weapon_profile_evaluated"
            and isinstance(event.payload, dict)
            and event.payload.get("attack_context_id") in contexts
        ]
        assert len(evaluations) == 3
        evaluated_contexts: list[str] = []
        for item in evaluations:
            evaluated_context = item["attack_context_id"]
            assert isinstance(evaluated_context, str)
            evaluated_contexts.append(evaluated_context)
        assert set(evaluated_contexts) == set(contexts)


@pytest.mark.parametrize("fault", ["future", "completed", "generated", "actor", "source"])
def test_later_psychic_frontier_rejects_drift_without_consuming_the_choice(fault: str) -> None:
    session = _session(BattlePhase.SHOOTING)
    first = reach_psychic_request(session)
    status = session.submit_option(
        request_id=first.request_id, result_id="first-complete", option_id="keep-all-modifiers"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    current = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    host = active_attack_sequence_for_state(state)
    assert host is not None
    assert host.attack_index == 0
    raw = cast(dict[str, Any], deepcopy(current.to_payload()))
    if fault == "actor":
        raw["actor_id"] = "player-b"
    else:
        key = "effect_snapshot_sha256" if fault == "source" else "attack_context_id"
        value = {
            "future": replace(host, attack_index=2).attack_context_id(),
            "completed": _context(first),
            "generated": _context(current) + ":generated-001",
            "source": "0" * 64,
        }[fault]
        raw["payload"][key] = value
        for option in raw["options"]:
            option["payload"][key] = value
    forged = DecisionRequest.from_payload(cast(DecisionRequestPayload, raw))
    result = DecisionResult.for_request(
        request=forged, selected_option_id="keep-all-modifiers", result_id="forged-current"
    )
    before = session.lifecycle.to_payload()
    config = before["config"]
    assert config is not None
    registry = build_runtime_content_bundle_for_armies(
        config=GameConfig.from_payload(config), armies=tuple(state.army_definitions)
    ).runtime_modifier_registry
    invalid = invalid_psychic_modifier_status(
        state=state,
        decisions=session.lifecycle.decision_controller,
        request=forged,
        result=result,
        runtime_modifier_registry=registry,
    )
    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    payload = cast(dict[str, Any], deepcopy(before))
    payload["decisions"]["queue"]["pending_requests"][0] = raw
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] == "decision_requested" and event["payload"]["request_id"] == (
            current.request_id
        ):
            event["payload"] = deepcopy(raw)
    with pytest.raises((GameLifecycleError, DecisionError)):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, payload))
    assert canonical_json(session.lifecycle.to_payload()) == canonical_json(before)
    status = session.submit_option(
        request_id=current.request_id, result_id="legal-retry", option_id="keep-all-modifiers"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID


@pytest.mark.parametrize("fault", ["skipped", "reordered"])
def test_restore_requires_an_ordered_completed_psychic_preparation_prefix(fault: str) -> None:
    session = _session(BattlePhase.SHOOTING)
    current = reach_psychic_request(session)
    contexts: list[str] = []
    for _ in range(2):
        contexts.append(_context(current))
        status = session.submit_option(
            request_id=current.request_id,
            result_id=f"{current.request_id}:complete",
            option_id="keep-all-modifiers",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        current = pending_request(session)
    assert not _hits(session)
    _assert_checkpoint(session)
    substitutions = (
        {contexts[0]: _context(current)}
        if fault == "skipped"
        else {contexts[0]: contexts[1], contexts[1]: contexts[0]}
    )
    before = session.lifecycle.to_payload()
    payload = deepcopy(before)

    def rewrite(value: JsonValue) -> None:
        if isinstance(value, list):
            for item in value:
                rewrite(item)
        elif isinstance(value, dict):
            context = value.get("attack_context_id")
            if isinstance(context, str) and context in substitutions:
                value["attack_context_id"] = substitutions[context]
            for item in value.values():
                rewrite(item)

    rewrite(cast(JsonValue, payload["decisions"]))
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)
    assert session.lifecycle.to_payload() == before
