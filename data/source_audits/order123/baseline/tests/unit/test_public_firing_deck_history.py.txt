"""Firing Deck clients can construct exact history evidence from public requests."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import cast

import pytest
from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.redaction import (
    public_decision_request_payload,
    public_event_record_payload,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_restriction_payload
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pose import Pose

HISTORY = "firing_deck_already_shot_unit_instance_ids"
TRANSPORT = "army-alpha:transport-1"
PRIOR = "army-alpha:prior"


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _pending(session: AdapterGameSession) -> dict[str, JsonValue]:
    pending = session.view(viewer_player_id="player-a")["pending_decision"]
    assert pending is not None
    return cast(dict[str, JsonValue], pending)


def _public_proposal(session: AdapterGameSession, *, cargo: bool) -> dict[str, JsonValue]:
    """Use only the projected proposal request; no lifecycle or roster lookups."""
    request = _object(_object(_pending(session)["payload"])["proposal_request"])
    weapons = request["available_weapons"]
    candidates = request["target_candidates"]
    assert isinstance(weapons, list)
    assert isinstance(candidates, list)
    weapon = next(
        _object(row)
        for row in weapons
        if ("firing_deck_source_unit_instance_id" in _object(row)) == cargo
    )
    candidate = next(
        _object(row)
        for row in candidates
        if _object(row)["weapon_instance_id"] == weapon["weapon_instance_id"]
        and _object(row)["is_legal"] is True
    )
    selection: JsonValue = None
    if cargo:
        selection = {
            "player_id": request["active_player_id"],
            "battle_round": request["battle_round"],
            "transport_unit_instance_id": request["unit_instance_id"],
            "firing_deck_value": request["firing_deck_value"],
            "already_shot_unit_instance_ids": request[HISTORY],
            "weapon_selections": [
                {
                    "embarked_unit_instance_id": weapon["firing_deck_source_unit_instance_id"],
                    "model_instance_id": weapon["firing_deck_source_model_instance_id"],
                    "weapon_instance_id": weapon["weapon_instance_id"],
                    "wargear_id": weapon["wargear_id"],
                    "weapon_profile": weapon["weapon_profile"],
                }
            ],
        }
    return {
        "proposal_request_id": request["request_id"],
        "proposal_kind": request["proposal_kind"],
        "player_id": request["active_player_id"],
        "battle_round": request["battle_round"],
        "unit_instance_id": request["unit_instance_id"],
        "source_decision_request_id": request["source_decision_request_id"],
        "source_decision_result_id": request["source_decision_result_id"],
        "visibility_cache_key": candidate["visibility_cache_key"],
        "firing_deck_selection": selection,
        "declarations": [
            {
                "attacker_model_instance_id": weapon["model_instance_id"],
                "weapon_instance_id": weapon["weapon_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile_id"],
                "target_unit_instance_id": candidate["target_unit_instance_id"],
                "shooting_type": request["selected_shooting_type"],
                "selected_weapon_ability_ids": [],
                "firing_deck_source_unit_instance_id": weapon.get(
                    "firing_deck_source_unit_instance_id"
                ),
                "firing_deck_source_model_instance_id": weapon.get(
                    "firing_deck_source_model_instance_id"
                ),
            }
        ],
    }


def _select(session: AdapterGameSession, unit_id: str) -> None:
    for option_id in (unit_id, "normal"):
        request = _pending(session)
        status = session.submit_option(
            request_id=cast(str, request["request_id"]),
            option_id=option_id,
            result_id=f"{unit_id}-{option_id}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status


def _session(*, prior_shot: bool = True) -> LocalGameSession:
    lifecycle, _units = _shooting_lifecycle(
        alpha_unit_ids=("prior", "passenger", "noncontributor", "transport-1"),
        alpha_datasheets={
            "transport-1": ("core-transport", "core-transport", 1),
        },
        embarked_unit_ids=("passenger", "noncontributor"),
        enemy_pose=Pose.at(28.0, 40.0),
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    session.advance_until_decision_or_terminal()
    if prior_shot:
        _select(session, PRIOR)
        proposal = _public_proposal(session, cargo=False)
        status = session.submit_parameterized_payload(
            request_id=cast(str, proposal["proposal_request_id"]),
            result_id="public-prior-shot",
            payload=proposal,
        )
        for index in range(32):
            request = _pending(session)
            if request["decision_type"] == "select_shooting_unit":
                break
            options = request["options"]
            assert isinstance(options, list)
            status = session.submit_option(
                request_id=cast(str, request["request_id"]),
                option_id=cast(str, _object(options[0])["option_id"]),
                result_id=f"public-prior-drain-{index}",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
        else:
            raise AssertionError("Prior shooting did not complete.")
    _select(session, TRANSPORT)
    return session


@pytest.mark.parametrize("prior_shot", [False, True])
def test_public_firing_deck_after_shot_history(prior_shot: bool) -> None:
    session = _session(prior_shot=prior_shot)
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    expected = [PRIOR] if prior_shot else []
    assert list(state.shooting_phase_state.shot_unit_ids) == expected
    proposal = _public_proposal(session, cargo=True)
    assert _object(proposal["firing_deck_selection"])["already_shot_unit_instance_ids"] == expected
    for viewer in ("player-b", "player-a", "player-b"):
        pending = session.view(viewer_player_id=viewer)["pending_decision"]
        assert pending is not None
        assert _object(_object(pending["payload"])["proposal_request"])[HISTORY] == expected
        events = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert HISTORY in json.dumps(events)
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert _public_proposal(restored, cargo=True) == proposal
    assert _public_proposal(session.fork(), cargo=True) == proposal
    before = copy.deepcopy(session.lifecycle.to_payload())
    status = session.submit_parameterized_payload(
        request_id=cast(str, proposal["proposal_request_id"]),
        result_id="public-firing-deck",
        payload=proposal,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    restored_status = restored.submit_parameterized_payload(
        request_id=cast(str, proposal["proposal_request_id"]),
        result_id="public-firing-deck",
        payload=proposal,
    )
    assert restored_status == status
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert session.lifecycle.to_payload() != before
    state = session.lifecycle.state
    assert state is not None
    effect = next(e for e in state.persisting_effects if firing_deck_restriction_payload(e))
    assert effect.target_unit_instance_ids == ("army-alpha:noncontributor", "army-alpha:passenger")
    persisted = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(persisted).to_persistence_payload() == persisted
    )
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="public-firing-deck")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay.diagnostics


@pytest.mark.parametrize(
    "drift",
    [
        "empty_history",
        "extra_history",
        "actor",
        "round",
        "transport",
        "source",
        "copy",
        "profile",
        "request",
    ],
)
def test_invalid_public_firing_deck_is_atomic_and_retryable(drift: str) -> None:
    session = _session()
    original = _public_proposal(session, cargo=True)
    proposal = copy.deepcopy(original)
    selection = _object(proposal["firing_deck_selection"])
    if drift == "empty_history":
        selection["already_shot_unit_instance_ids"] = []
    elif drift == "extra_history":
        selection["already_shot_unit_instance_ids"] = [PRIOR, "army-alpha:passenger"]
    elif drift == "actor":
        selection["player_id"] = "player-b"
    elif drift == "round":
        selection["battle_round"] = 2
    elif drift == "transport":
        selection["transport_unit_instance_id"] = PRIOR
    elif drift == "source":
        proposal["source_decision_result_id"] = "stale-source"
    elif drift == "request":
        proposal["proposal_request_id"] = "stale-request"
    else:
        weapons = selection["weapon_selections"]
        assert isinstance(weapons, list)
        weapon = _object(weapons[0])
        if drift == "copy":
            weapon["weapon_instance_id"] = "invented-copy"
        else:
            _object(weapon["weapon_profile"])["profile_id"] = "invented-profile"
    before = copy.deepcopy(session.lifecycle.to_payload())
    status = session.submit_parameterized_payload(
        request_id=cast(str, original["proposal_request_id"]),
        result_id="invalid-deck",
        payload=proposal,
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert session.lifecycle.to_payload() == before
    status = session.submit_parameterized_payload(
        request_id=cast(str, original["proposal_request_id"]),
        result_id="valid-retry",
        payload=original,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def test_pending_history_restore_rejects_drift() -> None:
    session = _session()
    payload = copy.deepcopy(session.lifecycle.to_payload())
    # Pending state is a public promise: recovery must not preserve stale evidence.
    pending = session.lifecycle.decision_controller.queue.peek_next()
    assert pending is not None
    assert isinstance(pending.payload, dict)
    _object(pending.payload["proposal_request"])[HISTORY] = []
    with pytest.raises(GameLifecycleError, match="pending shot-history snapshot drifted"):
        GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert GameLifecycle.from_payload(payload).to_payload() == payload


@pytest.mark.parametrize("context", ["absent", "round", "player", "phase", "out_of_phase"])
def test_no_current_history_authority_outside_matching_phase(context: str) -> None:
    from warhammer40k_core.engine.phases.shooting_firing_deck import (
        firing_deck_shot_history_snapshot,
    )

    session = _session()
    state = session.lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    if context == "absent":
        state.shooting_phase_state = None
    elif context == "round":
        state.battle_round = 2
    elif context == "player":
        state.active_player_id = "player-b"
    elif context == "phase":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    else:
        from warhammer40k_core.engine.phases.shooting_requests import (
            request_out_of_phase_shooting_declaration,
        )

        status = request_out_of_phase_shooting_declaration(
            state=state,
            decisions=session.lifecycle.decision_controller,
            ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
            army_catalog=session.lifecycle.config.army_catalog,
            player_id="player-a",
            unit_instance_id=TRANSPORT,
            parent_phase=BattlePhase.SHOOTING,
            source_rule_id="core:fire-overwatch",
            source_decision_request_id="reaction-source",
            source_decision_result_id="reaction-result",
            source_context={},
        )
        assert status.decision_request is not None
        request = _object(_object(status.decision_request.payload)["proposal_request"])
        assert request[HISTORY] is None
    assert firing_deck_shot_history_snapshot(state) is None


def test_secret_request_and_event_redact_nested_history() -> None:
    session = _session()
    request = session.lifecycle.decision_controller.queue.peek_next()
    assert request is not None
    payload = copy.deepcopy(_object(request.payload))
    payload["secret"] = True
    secret = replace(request, payload=payload)
    owner = ViewerContext.for_player("player-a")
    opponent = ViewerContext.for_player("player-b")
    assert HISTORY in json.dumps(public_decision_request_payload(secret, viewer=owner))
    assert HISTORY not in json.dumps(public_decision_request_payload(secret, viewer=opponent))
    event = public_event_record_payload(
        event_id="secret-deck",
        event_type="decision_requested",
        payload=cast(JsonValue, secret.to_payload()),
        viewer=opponent,
    )
    assert HISTORY not in json.dumps(event)
