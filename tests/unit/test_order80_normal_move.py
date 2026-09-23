from __future__ import annotations

import json
from copy import deepcopy
from typing import cast

import pytest
from tests.normal_move_occurrence_helpers import (
    accept_reaction,
    next_player_action,
    reaction_request,
    reaction_session,
    request_from,
    submit_path,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


@pytest.mark.parametrize("parameterized", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_normal_move_reaction_does_not_consume_next_players_movement_phase(
    parameterized: bool,
    attached: bool,
) -> None:
    session, unit_id = reaction_session(attached=attached, parameterized=parameterized)
    status = accept_reaction(session, parameterized=parameterized)
    request = next_player_action(session, status, unit_id)
    assert "normal_move" in {o.option_id for o in request.options}
    for viewer in ("player-a", "player-b"):
        view = session.view(viewer_player_id=viewer)
        assert view["pending_decision"] is not None
        assert "normal_move" in {o["option_id"] for o in view["pending_decision"]["options"]}
    status = session.submit_option(
        request_id=request.request_id, option_id="normal_move", result_id="order80-own-normal"
    )
    submit_path(session, request_from(status), result_id="order80-own-normal-path")
    state = session.lifecycle.state
    assert state is not None
    assert len(state.normal_move_states) == 2
    assert [row.turn_player_id for row in state.normal_move_states] == ["player-a", "player-b"]
    assert {row.player_id for row in state.normal_move_states} == {"player-b"}
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order80-occurrence"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("parameterized", [False, True])
def test_ordinary_move_does_not_consume_opponents_reactive_phase(parameterized: bool) -> None:
    session, enemy_id = reaction_session(enqueue_reaction=False)
    request = request_from(session.advance_until_decision_or_terminal())
    action = request_from(
        session.submit_option(
            request_id=request.request_id, option_id="army-alpha:source", result_id="own-unit"
        )
    )
    proposal = request_from(
        session.submit_option(
            request_id=action.request_id, option_id="normal_move", result_id="own-action"
        )
    )
    status = submit_path(session, proposal, result_id="own-path")
    action = next_player_action(session, status, enemy_id)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="ordinary-first"))
        .run()
        .reproduced_exactly
    )
    # An explicit generic permission is the initial fixture of this second replay segment.
    reaction = reaction_request(session, "army-alpha:source", parameterized=parameterized)
    session.lifecycle.decision_controller.request_decision(reaction)
    session = LocalGameSession(session.lifecycle)
    session.advance_until_decision_or_terminal()
    initial = session.lifecycle.to_payload()
    session.submit_option(
        request_id=action.request_id, option_id="remain_stationary", result_id="enemy-stationary"
    )
    accept_reaction(session, parameterized=parameterized)
    state = session.lifecycle.state
    assert state is not None
    assert [(r.turn_player_id, r.player_id) for r in state.normal_move_states] == [
        ("player-a", "player-a"),
        ("player-b", "player-a"),
    ]
    assert (
        ReplayRunner(
            ReplayArtifact.capture(
                artifact_id="opponent-reaction",
                initial_lifecycle_payload=initial,
                final_lifecycle=session.lifecycle,
            )
        )
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("parameterized", [False, True])
def test_second_reaction_same_phase_is_decline_only(parameterized: bool) -> None:
    session, unit_id = reaction_session(parameterized=parameterized, attached=True)
    accept_reaction(session, parameterized=parameterized)
    if parameterized:
        request = reaction_request(session, unit_id, parameterized=True)
        assert [option.option_id for option in request.options] == ["decline_triggered_movement"]
    else:
        with pytest.raises(GameLifecycleError, match="normal_move_already_used_this_phase"):
            reaction_request(session, unit_id, parameterized=False)
    state = session.lifecycle.state
    assert state is not None
    for component_id in rules_unit_view_by_id(
        state=state, unit_instance_id=unit_id
    ).component_unit_instance_ids:
        assert (
            len(
                state.normal_move_states_for_unit_phase(
                    player_id="player-b",
                    battle_round=1,
                    phase=BattlePhase.MOVEMENT,
                    unit_instance_id=component_id,
                )
            )
            == 1
        )

    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model

    bodyguard = next(a for a in state.army_definitions if a.player_id == "player-b").unit_by_id(
        "army-beta:reactor"
    )
    for model in bodyguard.own_models:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )
    survivor = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    assert len(survivor.alive_models()) == 1
    assert (
        len(
            state.normal_move_states_for_unit_phase(
                player_id="player-b",
                battle_round=1,
                phase=BattlePhase.MOVEMENT,
                unit_instance_id="army-beta:leader",
            )
        )
        == 1
    )


@pytest.mark.parametrize("attached", [False, True])
def test_prior_opponent_reaction_preserves_current_turn_stationary_status(attached: bool) -> None:
    from warhammer40k_core.engine.phases.shooting_targeting import _rules_unit_remained_stationary

    session, unit_id = reaction_session(attached=attached)
    status = accept_reaction(session, parameterized=False)
    state = session.lifecycle.state
    assert state is not None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    assert not _rules_unit_remained_stationary(state=state, rules_unit=unit, player_id="player-b")
    action = next_player_action(session, status, unit_id)
    status = session.submit_option(
        request_id=action.request_id, option_id="remain_stationary", result_id="stay"
    )
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    overwatch = request_from(status)
    assert overwatch.decision_type == "submit_stratagem_target_proposal"
    session.submit_parameterized_payload(
        request_id=overwatch.request_id,
        result_id="decline-overwatch",
        payload=stratagem_decline_payload(),
    )
    session.advance_until_decision_or_terminal()
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert _rules_unit_remained_stationary(state=state, rules_unit=unit, player_id="player-b")
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="stationary"))
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize(
    "tamper",
    [
        "missing",
        "foreign",
        "turn",
        "phase",
        "removed",
        "duplicate",
        "source",
        "completion_turn",
        "completion_mode",
    ],
)
def test_restore_rejects_ambiguous_or_drifted_normal_move_occurrence(tamper: str) -> None:
    session, _ = reaction_session(parameterized=True)
    accept_reaction(session, parameterized=True)
    payload = deepcopy(session.lifecycle.to_payload())
    assert payload["state"] is not None
    row = payload["state"]["normal_move_states"][0]
    if tamper == "missing":
        del cast(dict[str, object], row)["turn_player_id"]
    elif tamper == "foreign":
        row["turn_player_id"] = "unknown"
    elif tamper in {"turn", "completion_turn"}:
        row["turn_player_id"] = "player-b"
        if tamper == "completion_turn":
            for event in payload["decisions"]["event_log"]:
                if event["event_type"] == "triggered_movement_resolved":
                    assert isinstance(event["payload"], dict)
                    event["payload"]["active_player_id"] = "player-b"
    elif tamper == "phase":
        row["phase"] = "shooting"
    elif tamper == "removed":
        payload["state"]["normal_move_states"] = []
    elif tamper == "duplicate":
        payload["state"]["normal_move_states"].append(deepcopy(row))
    elif tamper == "completion_mode":
        payload["state"]["normal_move_states"] = []
        for event in payload["decisions"]["event_log"]:
            if event["event_type"] == "triggered_movement_resolved":
                assert isinstance(event["payload"], dict)
                event["payload"]["movement_mode"] = "advance"
    else:
        row["source_rule_id"] = "invented-source"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_invalid_and_declined_requests_do_not_consume_normal_move() -> None:
    session, unit_id = reaction_session(parameterized=True)
    request = request_from(session.advance_until_decision_or_terminal())
    state = session.lifecycle.state
    assert state is not None
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="pending request"):
        session.submit_option(request_id="stale", option_id=unit_id, result_id="stale-result")
    assert state.to_payload() == before
    status = session.submit_option(
        request_id=request.request_id, option_id="decline_triggered_movement", result_id="decline"
    )
    assert state.normal_move_states == []
    action = next_player_action(session, status, unit_id)
    assert "normal_move" in {o.option_id for o in action.options}


def test_transport_disembark_classification_uses_current_occurrence() -> None:
    from dataclasses import replace

    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session

    from warhammer40k_core.engine.phases.movement_transports import (
        _disembark_candidates_for_movement_unit,
    )
    from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus

    session = disembark_session()
    selection = request_from(session.advance_until_decision_or_terminal())
    action = request_from(
        session.submit_option(
            request_id=selection.request_id, option_id=TRANSPORT_ID, result_id="transport"
        )
    )
    proposal = request_from(
        session.submit_option(
            request_id=action.request_id, option_id="normal_move", result_id="transport-normal"
        )
    )
    submit_path(session, proposal, result_id="transport-path", dx=0)
    state = session.lifecycle.state
    assert state is not None
    movement = state.movement_phase_state
    assert movement is not None
    for turn_owner, expected_status, expected_mode in (
        ("player-a", TransportMovementStatus.NORMAL_MOVE, DisembarkModeKind.RAPID_DISEMBARK),
        (
            "player-b",
            TransportMovementStatus.REMAIN_STATIONARY,
            DisembarkModeKind.TACTICAL_DISEMBARK,
        ),
    ):
        # Compare the actual candidate consumer on two typed occurrence snapshots.
        snapshot = replace(state, active_player_id=turn_owner)
        candidates = _disembark_candidates_for_movement_unit(
            state=snapshot,
            movement_state=movement,
            unit_instance_id=PASSENGER_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
        assert [(c.transport_movement_status, c.disembark_mode) for c in candidates] == [
            (expected_status, expected_mode)
        ]


@pytest.mark.parametrize("attached", [False, True])
def test_historical_split_and_component_aliases_preserve_occurrence_restriction(
    attached: bool,
) -> None:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
    from warhammer40k_core.engine.unit_splitting import build_split_army

    session, unit_id = reaction_session(attached=attached)
    accept_reaction(session, parameterized=False)
    state = session.lifecycle.state
    assert state is not None
    army = next(army for army in state.army_definitions if army.player_id == "player-b")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    split = build_split_army(
        army=army,
        unit_instance_id=unit_id,
        first_model_ids=tuple(model.model_instance_id for model in unit.alive_models())[::2],
        request_id="lineage-fixture",
        source_id="test:split-history",
        specified_strengths=None,
    )
    # A pure lineage-consumer fixture, not permission to split during gameplay.
    assert session.lifecycle.config is not None
    snapshot = GameState.from_config(session.lifecycle.config)
    for original in state.army_definitions:
        snapshot.record_army_definition(split if original is army else original)
    snapshot.record_normal_move_state(state.normal_move_states[0])
    for successor in rules_unit_views_from_armies(armies=(split,)):
        for identity in (successor.unit_instance_id, *successor.component_unit_instance_ids):
            for turn, phase, round_number, expected in (
                ("player-a", BattlePhase.MOVEMENT, 1, 1),
                ("player-b", BattlePhase.MOVEMENT, 1, 0),
                ("player-a", BattlePhase.SHOOTING, 1, 0),
                ("player-a", BattlePhase.MOVEMENT, 2, 0),
            ):
                snapshot.active_player_id = turn
                assert (
                    len(
                        snapshot.normal_move_states_for_unit_phase(
                            player_id="player-b",
                            battle_round=round_number,
                            phase=phase,
                            unit_instance_id=identity,
                        )
                    )
                    == expected
                )


def test_invalid_pending_reactive_proposal_does_not_consume_normal_move() -> None:
    session, unit_id = reaction_session(parameterized=True)
    selection = request_from(session.advance_until_decision_or_terminal())
    proposal = request_from(
        session.submit_option(
            request_id=selection.request_id,
            option_id=next(
                o.option_id
                for o in selection.options
                if o.option_id != "decline_triggered_movement"
            ),
            result_id="choose-reactor",
        )
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.active_player_id == "player-a"
    assert state.effective_active_player_id() == "player-b"
    assert state.active_player_scopes[0].unit_instance_id == unit_id
    before = state.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=proposal.request_id, result_id="malformed", payload={}
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    with pytest.raises(GameLifecycleError, match="pending request"):
        session.submit_parameterized_payload(
            request_id="old-proposal", result_id="stale-proposal", payload={}
        )
    assert state.to_payload() == before
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    submit_path(restored, proposal, result_id="valid-proposal")
    assert restored.lifecycle.state is not None
    assert restored.lifecycle.state.normal_move_states[0].turn_player_id == "player-a"
