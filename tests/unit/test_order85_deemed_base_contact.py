# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.order85_overhang_helpers import overhang_charge_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.base_contact_authority import current_deemed_base_contacts
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def test_all_placement_owners_reject_physical_overhang_overlap() -> None:
    from warhammer40k_core.engine import (
        deployment_geometry,
        prebattle,
        reserves,
        return_placement_legality,
        transport_disembark_geometry,
    )
    from warhammer40k_core.engine.phases.movement_geometry import (
        _enemy_model_ids_crossed_by_witness,
    )
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.model_body import ModelBodyPart
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    mover = Model("mover", Pose.at(10, 10), CircularBase(0.5), ModelVolume(1))
    enemy = Model(
        "enemy",
        Pose.at(11.5, 10),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(ModelBodyPart("body", CircularBase(2), 0, 0, 0, 1, "measured:body"),),
    )
    assert not mover.base_overlaps(enemy)
    for predicate in (
        deployment_geometry._models_overlap_with_volume,
        prebattle._models_overlap_with_volume,
        reserves._models_overlap_with_volume,
        transport_disembark_geometry._models_overlap_with_volume,
        return_placement_legality._models_overlap,
    ):
        assert predicate(mover, enemy), predicate.__module__
        assert not predicate(replace(mover, pose=Pose.at(5, 10)), enemy)
    assert _enemy_model_ids_crossed_by_witness(
        moving_model=mover,
        enemy_models=(enemy,),
        witness=PathWitness.for_paths((("mover", (Pose.at(10, 8), Pose.at(10, 12))),)),
    ) == ("enemy",)


def test_overhang_charge_is_accepted_and_persistent_contact_replays() -> None:
    session, proposal = overhang_charge_session()
    status = session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id="overhang-charge",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(current_deemed_base_contacts(session.lifecycle.state)) == 1
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    assert len(current_deemed_base_contacts(restored.lifecycle.state)) == 1
    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer)["pending_proposal"] is not None
        public = json.dumps(restored.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "deemed_base_contacts" in public
        assert "base_contact_query" not in public
        assert "movement_query" not in public
        assert "without_overhang_witness" not in public
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order85")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_body_penetration_is_rejected_without_contact_then_retry_succeeds() -> None:
    session, proposal = overhang_charge_session()
    assert proposal.witness is not None
    model_id = proposal.witness.model_ids()[0]
    start = proposal.witness.poses_for_model(model_id)[0]
    bad = replace(
        proposal, witness=PathWitness.for_paths(((model_id, (start, Pose.at(10, 10.35))),))
    )
    status = session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id="penetrating-charge",
        payload=cast(JsonValue, bad.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert not current_deemed_base_contacts(session.lifecycle.state)
    assert not any(
        e.event_type == "charge_move_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    retry = replace(proposal, proposal_request_id=request.request_id)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="retry",
        payload=cast(JsonValue, retry.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(current_deemed_base_contacts(session.lifecycle.state)) == 1


def test_deemed_contact_prevents_pile_in_rotation_and_stationary_retry_replays() -> None:
    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.movement_proposals import ProposalKind

    session, charge = overhang_charge_session()
    status = session.submit_parameterized_payload(
        request_id=charge.proposal_request_id,
        result_id="charge",
        payload=cast(JsonValue, charge.to_payload()),
    )
    request = status.decision_request
    assert request is not None
    assert charge.witness is not None
    model_id = charge.witness.model_ids()[0]
    end = charge.witness.final_pose_for_model(model_id)
    rotated = Pose.at(end.position.x, end.position.y, end.position.z, facing_degrees=90)
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=charge.unit_instance_id,
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(((model_id, (end, rotated)),)),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="illegal-rotation",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert "base_contact_model_moved" in json.dumps(status.to_payload())
    retry_request = session.advance_until_decision_or_terminal().decision_request
    assert retry_request is not None
    retry = replace(
        proposal,
        proposal_request_id=retry_request.request_id,
        witness=PathWitness.for_paths(((model_id, (end, end)),)),
    )
    status = session.submit_parameterized_payload(
        request_id=retry_request.request_id,
        result_id="stationary-pile-in",
        payload=cast(JsonValue, retry.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order85-pile-in"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "corruption",
    [
        "source",
        "missing",
        "round",
        "geometry",
        "budget",
        "duplicate",
        "query",
        "policy",
        "constraints",
    ],
)
def test_restore_rejects_correlated_contact_evidence_forgery(corruption: str) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.geometry.pose import GeometryError

    session, charge = overhang_charge_session()
    session.submit_parameterized_payload(
        request_id=charge.proposal_request_id,
        result_id="charge",
        payload=cast(JsonValue, charge.to_payload()),
    )
    raw = json.loads(json.dumps(session.lifecycle.to_payload()))

    def corrupt(value: object) -> None:
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            if "base_contacts" in value and corruption == "round":
                value["turn_player_id"] = "player-b"
            if "base_contact_query" in value and corruption == "query":
                del value["base_contact_query"]
            if "path_context" in value:
                if corruption == "policy":
                    value["path_context"]["may_end_in_enemy_engagement"] = False
                elif corruption == "constraints":
                    value["coherency_max_span_inches"] = 100.0
            for key in ("base_contacts", "deemed_base_contacts"):
                if key not in value:
                    continue
                contacts = value[key]
                if corruption == "missing":
                    value[key] = []
                elif corruption == "duplicate":
                    value[key] = contacts * 2
                else:
                    for contact in contacts:
                        if corruption == "source":
                            contact["source_rule_id"] = "forged-source"
                        elif corruption == "geometry":
                            contact["movement_query"]["path_context"]["enemy_models"][0][
                                "body_parts"
                            ][0]["evidence_id"] = "forged-geometry"
                        elif corruption == "budget":
                            contact["movement_query"]["path_context"][
                                "movement_distance_budget_inches"
                            ] = 40.0
            for child in value.values():
                corrupt(child)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                corrupt(child)

    corrupt(raw)
    with pytest.raises((GameLifecycleError, GeometryError)):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, raw))


@pytest.mark.parametrize(
    ("consolidate", "attached", "second_enemy"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, False),
        (True, False, True),
    ],
)
def test_fight_move_establishes_contact_without_a_charge_and_round_trips(
    consolidate: bool, attached: bool, second_enemy: bool
) -> None:
    from tests.order85_overhang_helpers import overhang_session

    from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, MovementMode
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
    from warhammer40k_core.engine.phase import BattlePhase

    session = overhang_session(
        phase=BattlePhase.FIGHT,
        start_y=9.0,
        consolidate=consolidate,
        attached=attached,
        second_enemy=second_enemy,
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    state = session.lifecycle.state
    assert state is not None
    model_id = (
        state.army_definitions[0].unit_by_id("army-alpha:source").own_models[0].model_instance_id
    )
    end = Pose.at(10, 14 - 4.0 - 20.0 / 25.4)
    assert state.battlefield_state is not None
    paths = tuple(
        (p.model_instance_id, (p.pose, end if p.model_instance_id == model_id else p.pose))
        for u in state.battlefield_state.placed_armies[0].unit_placements
        for p in u.model_placements
    )
    end = Pose.at(10, 14 - 4.0 - 20.0 / 25.4)
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE if consolidate else ProposalKind.PILE_IN,
        unit_instance_id=MovementProposalRequest.from_decision_request_payload(
            request.payload
        ).unit_instance_id,
        movement_phase_action="consolidate" if consolidate else "pile_in",
        movement_mode=MovementMode.CONSOLIDATE if consolidate else MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=() if consolidate else ("army-beta:enemy",),
        consolidate_target_unit_instance_ids=(
            ("army-beta:enemy", "army-beta:second") if second_enemy else ("army-beta:enemy",)
        )
        if consolidate
        else (),
        consolidation_mode=ConsolidationModeKind.ONGOING if consolidate else None,
        witness=PathWitness.for_paths(paths),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="fight-contact",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.to_payload()
    contacts = current_deemed_base_contacts(state)
    assert any(c.moving_model_id == model_id for c in contacts) is not second_enemy
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="fight-contact")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_contact_rechecks_current_geometry_and_does_not_rewrite_target_ranges() -> None:
    from warhammer40k_core.engine.base_contact_authority import engine_models_in_base_contact
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.fight_geometry import attack_targetable_engaged_enemy_unit_ids
    from warhammer40k_core.engine.physical_engagement import physical_geometry_models_for_rules_unit

    session, charge = overhang_charge_session()
    session.submit_parameterized_payload(
        request_id=charge.proposal_request_id,
        result_id="charge",
        payload=cast(JsonValue, charge.to_payload()),
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    scenario = battlefield_scenario_for_state(state=state)
    source = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id="army-alpha:source"
    )[0]
    target = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id="army-beta:enemy"
    )[0]
    assert engine_models_in_base_contact(source, target, state=state)
    assert engine_models_in_base_contact(target, source, state=state)
    assert math.isclose(source.range_to(target), 4.0 - 60.0 / 25.4)
    assert attack_targetable_engaged_enemy_unit_ids(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=state.battlefield_state.unit_placement_by_id("army-alpha:source"),
        state=state,
    ) == ("army-beta:enemy",)
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:source")
    moved = placement.with_model_placements(
        (placement.model_placements[0].with_pose(Pose.at(10, 9)),)
    )
    state.replace_battlefield_state(state.battlefield_state.with_unit_placement(moved))
    source = replace(source, pose=Pose.at(10, 9))
    assert not engine_models_in_base_contact(source, target, state=state)


@pytest.mark.parametrize("boundary", ["other-turn", "next-round", "cleanup"])
def test_contact_expires_at_turn_boundary(boundary: str) -> None:
    from warhammer40k_core.engine.battlefield_state import BattlefieldTransitionBatch
    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState

    session, charge = overhang_charge_session()
    session.submit_parameterized_payload(
        request_id=charge.proposal_request_id,
        result_id="charge",
        payload=cast(JsonValue, charge.to_payload()),
    )
    state = session.lifecycle.state
    assert state is not None
    assert current_deemed_base_contacts(state)
    if boundary == "other-turn":
        state.active_player_id = "player-b"
    elif boundary == "next-round":
        state.battle_round += 1
    else:
        state.end_turn_cleanup_states.append(
            EndTurnCleanupState(
                cleanup_id="order85-end",
                game_id=state.game_id,
                battle_round=1,
                active_player_id="player-a",
                phase="fight",
                removals=(),
                coherency_results=(),
                transition_batch=BattlefieldTransitionBatch(displacements=()),
            )
        )
    assert not current_deemed_base_contacts(state)


def test_opponent_turn_movement_contact_uses_turn_owner_and_present_physical_ids() -> None:
    from tests.order85_overhang_helpers import overhang_session

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
    from warhammer40k_core.engine.phase import BattlePhase

    session = overhang_session(phase=BattlePhase.FIGHT, start_y=9.0, turn_owner="player-b")
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    pending = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert pending.unit_instance_id == "army-beta:enemy"
    no_move = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=pending.unit_instance_id,
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
    )
    request = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="enemy-stationary",
        payload=cast(JsonValue, no_move.to_payload()),
    ).decision_request
    assert request is not None
    state = session.lifecycle.state
    assert state is not None
    mover_id = state.army_definitions[0].units[0].own_models[0].model_instance_id
    move = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id="army-alpha:source",
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(
            ((mover_id, (Pose.at(10, 9), Pose.at(10, 14 - 4 - 20 / 25.4))),)
        ),
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="opponent-turn-contact",
        payload=cast(JsonValue, move.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    contacts = current_deemed_base_contacts(state)
    assert len(contacts) == 1
    assert state.model_movement_history[-1].turn_player_id == "player-b"
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="opponent-turn")).run().status
        is ReplayRunStatus.REPRODUCED
    )
    assert state.battlefield_state is not None
    original = state.battlefield_state
    state.replace_battlefield_state(original.with_removed_models((contacts[0].enemy_model_id,)))
    assert not current_deemed_base_contacts(state)
    state.replace_battlefield_state(original)
    assert current_deemed_base_contacts(state) == contacts
    state.active_player_id = "player-a"
    assert not current_deemed_base_contacts(state)


@pytest.mark.parametrize("corruption", ["permission", "unknown"])
def test_fight_contact_restore_rejects_forged_capabilities(corruption: str) -> None:
    from tests.order85_overhang_helpers import overhang_session

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
    from warhammer40k_core.geometry.pose import GeometryError

    session = overhang_session(phase=BattlePhase.FIGHT, start_y=9)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    state = session.lifecycle.state
    assert state is not None
    mid = state.army_definitions[0].units[0].own_models[0].model_instance_id
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id="army-alpha:source",
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(((mid, (Pose.at(10, 9), Pose.at(10, 14 - 4 - 20 / 25.4))),)),
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="contact",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    raw = json.loads(json.dumps(session.lifecycle.to_payload()))
    changed = 0

    def corrupt(value: object) -> None:
        nonlocal changed
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            if "path_context" in value:
                changed += 1
                if corruption == "permission":
                    value["path_context"]["may_transit_enemy_models"] = True
                else:
                    value["path_context"]["moving_model"]["untrusted_permission"] = True
            for item in value.values():
                corrupt(item)
        elif isinstance(value, list):
            for item in cast(list[object], value):
                corrupt(item)

    corrupt(raw)
    assert changed >= 3
    with pytest.raises((GeometryError, GameLifecycleError)):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, raw))


def test_surge_contact_uses_surge_permissions_on_restore_and_replay() -> None:
    from tests.order85_overhang_helpers import overhang_session
    from tests.surge_helpers import surge_descriptor

    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.triggered_movement import TriggeredMovementEligibleUnit
    from warhammer40k_core.engine.triggered_movement_selection import (
        triggered_movement_unit_selection_request,
    )

    lifecycle = overhang_session(phase=BattlePhase.SHOOTING).lifecycle
    state = lifecycle.state
    assert state is not None
    descriptor = surge_descriptor(lifecycle=lifecycle)
    selection = triggered_movement_unit_selection_request(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(
                "army-alpha:source", "test:hook", descriptor.source_rule_id
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(selection)
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    request = session.submit_option(
        request_id=selection.request_id,
        result_id="select-surge",
        option_id="surge:army-alpha:source:target:army-beta:enemy",
    ).decision_request
    assert request is not None
    pending = MovementProposalRequest.from_decision_request_payload(request.payload)
    mid = state.army_definitions[0].units[0].own_models[0].model_instance_id
    proposal = MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=pending.proposal_kind,
        unit_instance_id=pending.unit_instance_id,
        movement_phase_action="surge_move",
        witness=PathWitness.for_paths(((mid, (Pose.at(10, 8), Pose.at(10, 14 - 4 - 20 / 25.4))),)),
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="surge-contact",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, result.to_payload()
    assert len(current_deemed_base_contacts(state)) == 1
    checkpoint = session.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(checkpoint))
        ).to_persistence_payload()
        == checkpoint
    )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="surge-contact")).run().status
        is ReplayRunStatus.REPRODUCED
    )
