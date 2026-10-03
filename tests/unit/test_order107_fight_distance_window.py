"""FAQ 9657bb5d: extra Fight movement belongs to its matching phase step."""

import json
from typing import cast

import pytest
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
)
from warhammer40k_core.engine.fight_resolution import fight_movement_maximum_distance_inches
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def _session(*, attached: bool) -> LocalGameSession:
    poses = {
        "source": tuple(Pose.at(10, 10 + 1.8 * i) for i in range(5))
        if attached
        else (Pose.at(10, 10),),
        "enemy": tuple(Pose.at(15.1, 10 + 1.8 * i) for i in range(5))
        if attached
        else (Pose.at(15.1, 10),),
    }
    specs = {"leader": ("core-character-leader", "core-character-leader", 1)}
    if attached:
        poses["leader"] = (Pose.at(10, 8.2),)
        poses["enemy-leader"] = (Pose.at(15.1, 8.2),)
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("source", "leader") if attached else ("source",),
        enemy_unit_ids=("enemy", "enemy-leader") if attached else ("enemy",),
        origins={key: value[0] for key, value in poses.items()},
        poses_by_unit_key=poses,
        game_id=f"order107-{attached}",
        datasheet_id="core-intercessor-like-infantry" if attached else "core-character-leader",
        model_profile_id="core-intercessor-like" if attached else "core-character-leader",
        model_count=5 if attached else 1,
        alpha_unit_specs=specs if attached else None,
        enemy_unit_specs={"enemy-leader": specs["leader"]} if attached else None,
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "source"),)
        if attached
        else (),
        enemy_attachment_declarations=(AttachmentDeclaration("enemy-leader", "enemy"),)
        if attached
        else (),
        charge_fights_first_unit_keys=("source",),
    )
    state = lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="order107:distance",
            source_rule_id="test:order107:distance",
            owner_player_id="player-a",
            target_unit_instance_ids=(units["leader" if attached else "source"].unit_instance_id,),
            started_battle_round=1,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": "test:order107:distance",
                "pile_in_distance_inches": 6.0,
                "consolidate_distance_inches": 5.0,
            },
        )
    )
    return LocalGameSession(lifecycle)


def _restore(session: LocalGameSession) -> LocalGameSession:
    payload = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(payload)))
    assert restored.to_persistence_payload() == payload
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    return restored


def _move(session: LocalGameSession, *, dx: float, result_id: str) -> LifecycleStatus:
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert move.context is not None
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    paths = tuple(
        (
            item.model_instance_id,
            (item.pose, Pose.at(item.pose.position.x + dx, item.pose.position.y)),
        )
        for army in state.battlefield_state.placed_armies
        for unit in army.unit_placements
        if unit.player_id == "player-a"
        for item in unit.model_placements
    )
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload={
            "proposal_request_id": move.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": move.movement_phase_action,
            "movement_mode": "pile_in",
            "pile_in_target_unit_instance_ids": move.context["legal_target_unit_instance_ids"],
            "witness": cast(JsonValue, PathWitness.for_paths(paths).to_payload()),
        },
    )


def _overrun(session: LocalGameSession) -> LocalGameSession:
    for _ in range(20):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            if move.context is not None and move.context.get("fight_movement_timing") == "overrun":
                return session
        submit_fixture_request(session, request)
    raise AssertionError("Expected legal Overrun after declining initial Pile In")


@pytest.mark.parametrize("attached", [False, True])
def test_overrun_request_uses_core_distance(attached: bool) -> None:
    session = _overrun(_session(attached=attached))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert move.context is not None
    assert move.context["maximum_distance_inches"] == 3.0


@pytest.mark.parametrize("attached", [False, True])
def test_overrun_rejects_extra_distance_then_restores_retries_and_replays(attached: bool) -> None:
    session = _restore(_overrun(_session(attached=attached)))
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    status = _move(session, dx=3.5, result_id="overrun-too-far")
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert state.battlefield_state == before
    session = _restore(session)
    status = _move(session, dx=3.0, result_id="overrun-legal")
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    session = _restore(session)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="overrun-retry")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("attached", [False, True])
def test_matching_pile_in_step_keeps_extra_distance_and_historical_restore(attached: bool) -> None:
    session = _session(attached=attached)
    session.advance_until_decision_or_terminal()
    session = _restore(session)
    status = _move(session, dx=3.5, result_id="pile-in-extra")
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    for _ in range(10):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "select_fight_activation":
            break
        submit_fixture_request(session, request)
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.current_step is FightPhaseStepKind.FIGHT
    session = _restore(session)
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="pile-in-history"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("phase", [BattlePhase.FIGHT, BattlePhase.SHOOTING])
@pytest.mark.parametrize("step", list(FightPhaseStepKind))
@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
def test_extra_distance_requires_matching_phase_and_step(
    phase: BattlePhase, step: FightPhaseStepKind, kind: ProposalKind
) -> None:
    session = _session(attached=False)
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    state.replace_fight_phase_state(
        state.fight_phase_state.with_current_step(
            current_step=step, policy=state.runtime_ruleset_descriptor().fight_policy
        )
    )
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    expected_step = (
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE
    )
    expected = (
        (6.0 if kind is ProposalKind.PILE_IN else 5.0)
        if (phase is BattlePhase.FIGHT and step is expected_step)
        else 3.0
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state, unit_instance_id="army-alpha:source", proposal_kind=kind
        )
        == expected
    )
