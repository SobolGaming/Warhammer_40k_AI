"""Public movement clients join canonical actors to current physical models."""

from dataclasses import replace
from typing import cast

import pytest
from tests.charge_distance_helpers import charge_session, select_source, select_targets
from tests.charge_endpoint_helpers import attached_charge_session, select_attached_source
from tests.public_membership_helpers import attached_split_config

from warhammer40k_core.adapters.battlefield_projection import BattlefieldModelEntityPayload
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind, SetupStep
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def _models(
    session: AdapterGameSession, viewer: str = "player-a"
) -> dict[str, BattlefieldModelEntityPayload]:
    battlefield = session.view(viewer_player_id=viewer)["battlefield_view"]
    assert battlefield is not None
    return battlefield["authoritative"]["models_by_id"]


def _public_charge(session: AdapterGameSession, request: DecisionRequest) -> ChargeMoveProposal:
    """All actor membership and starts come from public, viewer-scoped data."""
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal_request.context is not None
    target_selection = proposal_request.context["target_selection"]
    assert isinstance(target_selection, dict)
    targets = target_selection["target_ids"]
    assert isinstance(targets, list)
    models = _models(session)
    target_positions = [
        row["pose"]["position"]
        for row in models.values()
        if row["rules_unit_instance_id"] in targets
        and row["pose"] is not None
        and row["state"] == "placed"
    ]
    front = min(p["y_inches"] for p in target_positions)
    right = max(p["x_inches"] for p in target_positions)
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for model in models.values():
        if (
            model["rules_unit_instance_id"] != proposal_request.unit_instance_id
            or model["state"] != "placed"
        ):
            continue
        pose = model["pose"]
        assert pose is not None
        p = pose["position"]
        start = Pose.at(
            p["x_inches"], p["y_inches"], p["z_inches"], facing_degrees=pose["facing_degrees"]
        )
        # This scene has a straight clear approach: stop in front of the row,
        # or alongside its right edge. No private ownership drives the path.
        end_y = front - (1 if p["x_inches"] > right else 2)
        paths.append((model["model_instance_id"], (start, Pose.at(p["x_inches"], end_y))))
    assert paths
    return ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=tuple(cast(str, value) for value in targets),
        witness=PathWitness.for_paths(tuple(paths)),
    )


@pytest.mark.parametrize("attached", [False, True])
def test_public_client_completes_charge_and_restores_current_membership(attached: bool) -> None:
    session = attached_charge_session() if attached else charge_session()
    request = select_attached_source(session) if attached else select_source(session)
    target = "army-beta:enemy" if attached else "army-beta:new"
    request = select_targets(session, request, (target,))
    proposal = _public_charge(session, request)
    before = _models(session)
    actor_models = {
        key: row
        for key, row in before.items()
        if row["rules_unit_instance_id"] == proposal.unit_instance_id and row["state"] == "placed"
    }
    assert len(actor_models) == (6 if attached else 5)
    assert {row["unit_instance_id"] for row in actor_models.values()} == (
        {"army-alpha:source", "army-alpha:leader"} if attached else {"army-alpha:source"}
    )
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert _models(restored) == before
    status = restored.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="public-charge",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    after = _models(restored)
    assert all(after[key]["pose"] != row["pose"] for key, row in actor_models.items())
    assert all(
        after[key]["unit_instance_id"] == row["unit_instance_id"] for key, row in before.items()
    )
    assert (
        _models(LocalGameSession.from_persistence_payload(restored.to_persistence_payload()))
        == after
    )
    assert _models(restored, "player-b") == after


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "missing_component",
        "foreign_model",
        "physical_actor",
        "stale_start",
        "targets",
        "invalid_path",
    ],
)
def test_public_charge_invalid_witness_is_atomic_and_can_retry(invalid_kind: str) -> None:
    session = attached_charge_session()
    request = select_targets(session, select_attached_source(session), ("army-beta:enemy",))
    proposal = _public_charge(session, request)
    assert proposal.witness is not None
    paths = proposal.witness.model_paths
    if invalid_kind == "missing_component":
        proposal = replace(proposal, witness=PathWitness.for_paths(paths[1:]))
    elif invalid_kind == "foreign_model":
        foreign = next(
            row
            for row in _models(session).values()
            if row["rules_unit_instance_id"] != proposal.unit_instance_id
        )
        proposal = replace(
            proposal,
            witness=PathWitness.for_paths(
                ((foreign["model_instance_id"], paths[0][1]), *paths[1:])
            ),
        )
    elif invalid_kind == "physical_actor":
        proposal = replace(proposal, unit_instance_id="army-alpha:leader")
    elif invalid_kind == "stale_start":
        model_id, poses = paths[0]
        proposal = replace(
            proposal,
            witness=PathWitness.for_paths(((model_id, (Pose.at(1, 1), poses[-1])), *paths[1:])),
        )
    elif invalid_kind == "targets":
        proposal = replace(proposal, charge_target_unit_instance_ids=("army-alpha:next",))
    else:
        model_id, poses = paths[0]
        proposal = replace(
            proposal,
            witness=PathWitness.for_paths(
                ((model_id, (poses[0], Pose.at(500, 500), poses[-1])), *paths[1:])
            ),
        )
    before = _models(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"invalid:{invalid_kind}",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert _models(session) == before
    pending = session.view(viewer_player_id="player-a")["pending_decision"]
    assert pending is not None
    retry = MovementProposalRequest.from_decision_request_payload(
        pending["payload"]
    ).to_decision_request()
    original_context = MovementProposalRequest.from_decision_request_payload(
        request.payload
    ).context
    retry_context = MovementProposalRequest.from_decision_request_payload(retry.payload).context
    assert retry_context == original_context
    valid = _public_charge(session, retry)
    accepted = session.submit_parameterized_payload(
        request_id=retry.request_id,
        result_id=f"retry:{invalid_kind}",
        payload=cast(JsonValue, valid.to_payload()),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted


def test_membership_tracks_private_split_reveal_and_checkpoint() -> None:
    session = LocalGameSession()
    session.start(attached_split_config())
    status = session.advance_until_decision_or_terminal()
    while True:
        request = status.decision_request
        assert request is not None
        if request.decision_type == "select_unit_split_membership":
            break
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"setup:{request.request_id}",
        )
    owner_before = _models(session)
    opponent_before = _models(session, "player-b")
    own_ids = {key for key, row in owner_before.items() if row["owner_player_id"] == "player-a"}
    assert len(own_ids) == 6
    original_actor_ids = {owner_before[key]["rules_unit_instance_id"] for key in own_ids}
    assert len(original_actor_ids) == 1
    assert all(opponent_before[key]["rules_unit_instance_id"] is None for key in own_ids)
    status = session.submit_option(
        request_id=request.request_id, option_id="split", result_id="split-public-membership"
    )
    for _ in range(6):
        request = status.decision_request
        assert request is not None
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"split:{request.request_id}",
        )
    owner_after = _models(session)
    actors = {owner_after[key]["rules_unit_instance_id"] for key in own_ids}
    assert len(actors) == 2
    assert actors.isdisjoint(original_actor_ids)
    assert _models(session, "player-b") == opponent_before
    assert (
        _models(LocalGameSession.from_persistence_payload(session.to_persistence_payload()))
        == owner_after
    )
    # Finish simultaneous formation declarations through the ordinary facade.
    for _ in range(50):
        state = session.lifecycle.state
        assert state is not None
        if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
            break
        request = status.decision_request
        assert request is not None
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"reveal:{request.request_id}",
        )
    else:
        pytest.fail("Formation declarations did not complete")
    revealed = _models(session, "player-b")
    assert {revealed[key]["rules_unit_instance_id"] for key in own_ids} == actors
    assert {revealed[key]["unit_instance_id"] for key in own_ids} == {
        owner_after[key]["unit_instance_id"] for key in own_ids
    }
    assert (
        _models(
            LocalGameSession.from_persistence_payload(session.to_persistence_payload()), "player-b"
        )
        == revealed
    )


def test_casualty_and_physical_removal_keep_lineage_but_refresh_witness_membership() -> None:
    session = attached_charge_session()
    before = _models(session)
    state = session.lifecycle.state
    assert state is not None
    actor = next(
        row["rules_unit_instance_id"]
        for row in before.values()
        if row["unit_instance_id"] == "army-alpha:leader"
    )
    assert actor is not None
    bodyguard_ids = tuple(
        key for key, row in before.items() if row["unit_instance_id"] == "army-alpha:source"
    )
    for model_id in bodyguard_ids:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=actor,
            model_instance_id=model_id,
            damage=100,
            damage_kind=DamageKind.NORMAL,
        )
    after = _models(session)
    assert all(after[key]["state"] == "destroyed" for key in bodyguard_ids)
    assert all(after[key]["rules_unit_instance_id"] == actor for key in bodyguard_ids)
    remaining = [
        row
        for row in after.values()
        if row["rules_unit_instance_id"] == actor and row["state"] == "placed"
    ]
    assert len(remaining) == 1
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.replace_battlefield_state(
        battlefield.with_removed_models((remaining[0]["model_instance_id"],))
    )
    removed = _models(session)
    assert removed[remaining[0]["model_instance_id"]]["state"] == "removed"
    assert removed[remaining[0]["model_instance_id"]]["pose"] is None
    assert not [
        row
        for row in removed.values()
        if row["rules_unit_instance_id"] == actor and row["state"] == "placed"
    ]
    assert _models(session, "player-b") == removed
