# pyright: reportPrivateUsage=false
"""Legal MONSTER setup/movement use the shared terrain policy and native authority."""

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.d06_embark_helpers import move_payload, state_of
from tests.d07_upper_floor_helpers import MONSTER, reach_monster_deployment, reach_monster_move
from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.lifecycle import GameLifecyclePayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def assert_preserved(session: LocalGameSession) -> None:
    payload = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(payload)))
    fork = session.fork()
    for other in (restored, fork):
        assert other.to_persistence_payload() == payload
        for role in PrincipalRole:
            players = (
                ("player-a", "player-b")
                if role in (PrincipalRole.PLAYER, PrincipalRole.COACH)
                else (None,)
            )
            for player in players:
                viewer = ViewerContext(
                    principal_id=f"d07:{role}:{player}",
                    role=role,
                    viewer_player_id=player,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                assert other.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert other.events_since_for_context(EventStreamCursor(), viewer=viewer) == (
                    session.events_since_for_context(EventStreamCursor(), viewer=viewer)
                )
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="d07:exact-replay")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def assert_native_movement_rejection(
    session: LocalGameSession,
    *,
    before: GameLifecyclePayload,
    old_request_id: str,
) -> None:
    """Rejected geometry changes only the native audit ledger and retry request."""
    after = session.lifecycle.to_payload()
    assert before["state"] is not None
    assert after["state"] is not None
    assert {k: v for k, v in after["state"].items() if k != "decision_request_count"} == {
        k: v for k, v in before["state"].items() if k != "decision_request_count"
    }
    assert after["config"] == before["config"]
    assert len(after["decisions"]["records"]) == len(before["decisions"]["records"]) + 1
    assert pending_request(session).request_id != old_request_id
    assert pending_request(session).decision_type == "submit_movement_proposal"


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.integration
@pytest.mark.replay
def test_native_monster_upper_floor_atomic_rejection_legal_retry_and_continuation(
    player: str,
) -> None:
    session, request = reach_monster_deployment(player=player)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:overhanging-setup",
        payload=deployment_placement_payload_for_request(
            session.lifecycle, request=request, pose_factory=lambda _i, _p, _m: Pose.at(16, 13, 3)
        ),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending_request(session) == request
    assert_preserved(session)
    valid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:fitting-setup",
        payload=deployment_placement_payload_for_request(
            session.lifecycle, request=request, pose_factory=lambda _i, _p, _m: Pose.at(13, 13, 3)
        ),
    )
    assert valid.status_kind is not LifecycleStatusKind.INVALID, valid.to_payload()
    state = state_of(session)
    monster = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == MONSTER
    )
    assert "MONSTER" in monster.own_models[0].keywords
    assert "INFANTRY" not in monster.own_models[0].keywords
    assert_preserved(session)
    request = reach_monster_move(session, player=player)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:overhanging-move",
        payload=move_payload(
            session,
            request,
            witness=straight_line_witness_for_unit(
                session.lifecycle, unit_instance_id=MONSTER, dx=3
            ),
        ),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert_native_movement_rejection(session, before=before, old_request_id=request.request_id)
    request = pending_request(session)
    fork = session.fork()
    fork_before = fork.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    proposal = move_payload(
        session,
        request,
        witness=straight_line_witness_for_unit(session.lifecycle, unit_instance_id=MONSTER, dx=-1),
    )
    for other in (session, restored):
        valid = other.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="d07:fitting-move",
            payload=proposal,
        )
        assert valid.status_kind is not LifecycleStatusKind.INVALID, valid.to_payload()
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert fork.to_persistence_payload() == fork_before
    assert fork.to_persistence_payload() != session.to_persistence_payload()
    assert_preserved(session)


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.integration
@pytest.mark.replay
def test_native_upper_floor_permission_belongs_to_each_model(
    player: str,
    attached: bool,
) -> None:
    from tests.d07_upper_floor_helpers import MIXED, model_ownership_config

    session, request = reach_monster_deployment(
        player=player,
        config=model_ownership_config(player=player, attached=attached),
    )
    view = rules_unit_view_by_id(state=state_of(session), unit_instance_id=MIXED)
    assert "INFANTRY" in view.keywords
    assert "VEHICLE" in view.keywords
    vehicle = next(model for model in view.own_models if "VEHICLE" in model.keywords)
    assert "INFANTRY" not in vehicle.keywords
    assert len(view.components) == (2 if attached else 1)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:borrowed-setup",
        payload=deployment_placement_payload_for_request(
            session.lifecycle,
            request=request,
            pose_factory=lambda i, _p, _m: Pose.at(10 + (i % 2) * 1.8, 10 + (i // 2) * 1.8, 3),
        ),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "lacks a keyword for the upper floor" in json.dumps(invalid.to_payload())
    assert session.lifecycle.to_payload() == before
    assert pending_request(session) == request
    assert_preserved(session)
    valid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:owned-setup",
        payload=deployment_placement_payload_for_request(
            session.lifecycle,
            request=request,
            pose_factory=lambda i, _p, m: Pose.at(
                10 + (i % 2) * 1.8,
                10 + (i // 2) * 1.8,
                0 if m == vehicle.model_instance_id else 3,
            ),
        ),
    )
    assert valid.status_kind is not LifecycleStatusKind.INVALID, valid.to_payload()
    assert_preserved(session)
    request = reach_monster_move(session, player=player, unit_id=view.unit_instance_id)
    before = session.lifecycle.to_payload()
    from tests.sequential_translation_helpers import leading_first_translation_paths

    from warhammer40k_core.geometry.pathing import PathWitness

    state = state_of(session)
    assert state.battlefield_state is not None
    paths = tuple(
        path
        for component_id in view.component_unit_instance_ids
        for path in straight_line_witness_for_unit(
            session.lifecycle, unit_instance_id=component_id, dx=-1
        ).model_paths
    )
    witness = PathWitness.for_paths(leading_first_translation_paths(paths, dx=-1, dy=0))
    # A different endpoint for the VEHICLE-only model cannot borrow its unit's INFANTRY.
    raised = PathWitness.for_paths(
        tuple(
            (
                model_id,
                tuple(
                    Pose.at(p.position.x, p.position.y, 3, facing_degrees=p.facing.degrees)
                    if index == len(path) - 1
                    else p
                    for index, p in enumerate(path)
                ),
            )
            if model_id == vehicle.model_instance_id
            else (model_id, path)
            for model_id, path in witness.model_paths
        )
    )
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:borrowed-move",
        payload=move_payload(session, request, witness=raised),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert_native_movement_rejection(session, before=before, old_request_id=request.request_id)
    request = pending_request(session)
    assert_preserved(session)
    valid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:owned-move",
        payload=move_payload(session, request, witness=witness),
    )
    assert valid.status_kind is not LifecycleStatusKind.INVALID, valid.to_payload()
    assert_preserved(session)


def assert_exact_history_terrain(
    session: LocalGameSession, *, event_type: str, expanded: bool
) -> None:
    """Native positive provenance plus opposite-representation/feature denials."""
    from warhammer40k_core.engine.base_contact_history import validate_base_contact_history
    from warhammer40k_core.engine.event_log import validate_json_value

    controller = session.lifecycle.decision_controller
    events = controller.event_log.records
    state = state_of(session)
    assert state.battlefield_state is not None
    features = state.battlefield_state.terrain_features
    volumes = [volume.to_payload() for feature in features for volume in feature.terrain_volumes()]
    assert volumes
    index = next(
        index for index in reversed(range(len(events))) if events[index].event_type == event_type
    )
    raw = cast(dict[str, Any], json.loads(json.dumps(events[index].payload)))
    resolution = raw["resolution"] if event_type == "fight_movement_completed" else raw
    results = resolution["path_validation_results"]
    assert results
    assert all(row["is_valid"] for row in results)
    for row in results:
        terrain = row["base_contact_query"]["terrain_context"]
        assert terrain["terrain"] == (volumes if expanded else [])
        assert terrain["terrain_features"] == [feature.to_payload() for feature in features]
        assert row["base_contact_query"]["path_context"]["terrain"] == []
    before = session.to_persistence_payload()
    for corruption in ("opposite_raw_representation", "missing_feature"):
        edited = cast(dict[str, Any], json.loads(json.dumps(raw)))
        changed_resolution = (
            edited["resolution"] if event_type == "fight_movement_completed" else edited
        )
        terrain = changed_resolution["path_validation_results"][0]["base_contact_query"][
            "terrain_context"
        ]
        if corruption == "opposite_raw_representation":
            terrain["terrain"] = [] if expanded else volumes
        else:
            terrain["terrain_features"] = []
        changed = replace(events[index], payload=validate_json_value(edited))
        expected_diagnostic = (
            "Charge move-completed model movement authority drifted"
            if event_type == "charge_move_completed"
            else "Deemed contact physical movement authority drifted"
        )
        with pytest.raises(GameLifecycleError, match=expected_diagnostic):
            validate_base_contact_history(
                state=state,
                events=(*events[:index], changed, *events[index + 1 :]),
                decisions=controller.records,
                runtime_content_bundle=session.lifecycle._runtime_content_bundle,
            )
        assert session.to_persistence_payload() == before


@pytest.mark.parametrize("player", ["player-a", "player-b"])
@pytest.mark.integration
@pytest.mark.replay
def test_native_attached_body_terrain_move_restores_forks_replays_and_continues(
    player: str,
) -> None:
    from tests.d06_embark_helpers import default_choice
    from tests.d07_upper_floor_helpers import MIXED, reach_body_terrain_move
    from tests.sequential_translation_helpers import leading_first_translation_paths

    from warhammer40k_core.geometry.pathing import PathWitness

    session, request = reach_body_terrain_move(player=player)
    unit = rules_unit_view_by_id(state=state_of(session), unit_instance_id=MIXED)
    assert len(unit.components) == 2
    assert len(unit.alive_models()) == 4
    paths = tuple(
        path
        for component in unit.component_unit_instance_ids
        for path in straight_line_witness_for_unit(
            session.lifecycle, unit_instance_id=component, dx=-0.5
        ).model_paths
    )
    valid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:body-terrain-legal-move",
        payload=move_payload(
            session,
            request,
            witness=PathWitness.for_paths(leading_first_translation_paths(paths, dx=-0.5, dy=0)),
        ),
    )
    assert valid.status_kind is not LifecycleStatusKind.INVALID, valid.to_payload()
    assert_exact_history_terrain(
        session, event_type="movement_activation_completed", expanded=False
    )
    assert_preserved(session)
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(payload)
    fork = session.fork()
    fork_before = fork.to_persistence_payload()
    for other in (session, restored):
        default_choice(other, pending_request(other))
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert session.to_persistence_payload() != payload
    assert fork.to_persistence_payload() == fork_before == payload
    assert_preserved(session)


@pytest.mark.integration
@pytest.mark.replay
def test_native_charge_and_pile_in_keep_expanded_history_terrain() -> None:
    from tests.charge_distance_helpers import request_from, select_targets
    from tests.d07_upper_floor_helpers import phase_body_terrain_history_session

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
    from warhammer40k_core.engine.physical_engagement import physical_geometry_models_for_rules_unit
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.pathing import PathWitness

    session = phase_body_terrain_history_session()
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id="army-alpha:source",
            result_id="d07:charge-source",
        )
    )
    request = select_targets(session, request, ("army-beta:second",), result_id="d07:charge-target")
    scenario = battlefield_scenario_for_state(state=state_of(session))
    source = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id="army-alpha:source"
    )[0]
    target = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id="army-beta:second"
    )[0]
    assert isinstance(source.base, CircularBase)
    assert isinstance(target.base, CircularBase)
    end = Pose.at(
        target.pose.position.x - source.base.radius - target.base.radius, target.pose.position.y
    )
    charge = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="army-alpha:source",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-beta:second",),
        witness=PathWitness.for_paths(((source.model_id, (source.pose, end)),)),
    )
    valid = session.submit_parameterized_payload(
        request_id=charge.proposal_request_id,
        result_id="d07:terrain-charge",
        payload=cast(JsonValue, charge.to_payload()),
    )
    assert valid.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, valid.to_payload()
    assert_exact_history_terrain(session, event_type="charge_move_completed", expanded=True)
    assert_preserved(session)
    request = pending_request(session)
    assert charge.witness is not None
    model_id = charge.witness.model_ids()[0]
    end = charge.witness.final_pose_for_model(model_id)
    pile_in = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=charge.unit_instance_id,
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=("army-beta:second",),
        witness=PathWitness.for_paths(((model_id, (end, end)),)),
    )
    valid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d07:terrain-pile-in",
        payload=cast(JsonValue, pile_in.to_payload()),
    )
    assert valid.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, valid.to_payload()
    assert_exact_history_terrain(session, event_type="fight_movement_completed", expanded=True)
    assert_preserved(session)
