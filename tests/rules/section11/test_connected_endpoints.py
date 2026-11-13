"""Connected endpoint certificates preserve legal Charge paths and persistence."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section11_attached import attached_case
from tests.support.section11_fixtures import (
    SPAWN,
    begin,
    choose,
    events,
    modifier,
    propose,
    roll,
    session_for,
    targets,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Point3, Pose


@pytest.mark.parametrize("range_inches", [None, 1.0])
def test_connected_endpoint_exclusion_requires_every_fixed_component(
    range_inches: float | None,
) -> None:
    from tests.support.section01_geometry import witnessed_query
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.charge_model_endpoints import (
        ChargeModelPathContext,
        charge_model_endpoint_witness,
    )
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.connected_endpoint_proof import (
        endpoint_excluded_by_connected_components,
    )
    from warhammer40k_core.geometry.movement_reachability import MovementGoal
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    source = Model("mover", Pose.at(5, 19.5), CircularBase(0.5), ModelVolume(1))
    lower = replace(source, model_id="lower", pose=Pose.at(10, 8))
    upper = replace(source, model_id="upper", pose=Pose.at(10, 18))
    target = replace(source, model_id="enemy", pose=Pose.at(10, 21))
    goal = MovementGoal(models=(target,), horizontal_inches=1, range_inches=range_inches)
    query = witnessed_query(source, Pose.at(10, 19.5), 8, goal, (target,))
    query = replace(query, coherent_models=(lower, upper))
    assert endpoint_excluded_by_connected_components(
        source=source, peers=query.coherent_models, goal=goal, horizontal_inches=2
    )
    row = charge_model_endpoint_witness(
        start=source,
        end=source,
        targets={"enemy-unit": (target,)},
        ruleset=RulesetDescriptor.warhammer_40000_eleventh(),
        context=ChargeModelPathContext("unit", query),
        component_unit_instance_id="unit",
    )
    assert row.preferred_reachability.status == "endpoint_unreachable"
    assert row.engagement_reachability.status == "endpoint_unreachable"

    # A distinct all-model-distance policy does not require this connectivity
    # graph. The same geometry must remain searchable under that policy.
    all_models = charge_model_endpoint_witness(
        start=source,
        end=source,
        targets={"enemy-unit": (target,)},
        ruleset=RulesetDescriptor.warhammer_40000_eleventh(),
        context=ChargeModelPathContext(
            "unit", replace(query, coherency_all_models_distance_inches=100)
        ),
        component_unit_instance_id="unit",
    )
    assert all_models.engagement_reachability.status == "reachable"

    # Changing the fixed peer layout admits a real legal alternative. The old
    # proof must neither survive the context change nor reject this path.
    moved = replace(lower, pose=Pose.at(10, 17))
    legal = replace(
        query,
        coherent_models=(moved, upper),
        path_context=replace(query.path_context, friendly_models=(moved, upper)),
    )
    assert not endpoint_excluded_by_connected_components(
        source=source, peers=legal.coherent_models, goal=goal, horizontal_inches=2
    )
    positive = charge_model_endpoint_witness(
        start=source,
        end=source,
        targets={"enemy-unit": (target,)},
        ruleset=RulesetDescriptor.warhammer_40000_eleventh(),
        context=ChargeModelPathContext("unit", legal),
        component_unit_instance_id="unit",
    )
    for evidence in (positive.preferred_reachability, positive.engagement_reachability):
        assert evidence.status == "reachable"
        assert evidence.alternative_witness is not None
        path = PathWitness.from_payload(evidence.alternative_witness)
        assert replace(legal.path_context, witness=path).validate().is_valid
        assert replace(legal.terrain_context, witness=path).validate().is_valid


@pytest.mark.parametrize("control", ["empty", "bridge", "union", "tangent", "shape", "body"])
def test_connected_endpoint_proof_relaxes_the_entire_goal_and_peer_graph(control: str) -> None:
    from warhammer40k_core.geometry.base import CircularBase, OvalBase
    from warhammer40k_core.geometry.connected_endpoint_proof import (
        endpoint_excluded_by_connected_components,
    )
    from warhammer40k_core.geometry.model_body import ModelBodyPart
    from warhammer40k_core.geometry.movement_reachability import MovementGoal
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    source = Model("mover", Pose.at(5, 19.5), CircularBase(0.5), ModelVolume(1))
    peers = tuple(replace(source, model_id=str(y), pose=Pose.at(10, y)) for y in (8, 18))
    target = replace(source, model_id="enemy", pose=Pose.at(10, 21))
    targets: tuple[Model, ...] = (target,)
    if control == "empty":
        peers = ()
    elif control == "bridge":
        peers += tuple(replace(source, model_id=str(y), pose=Pose.at(10, y)) for y in (11, 14, 17))
    elif control == "union":
        targets += (replace(target, model_id="other-enemy", pose=Pose.at(10, 9.5)),)
    elif control == "tangent":
        peers = (replace(peers[0], pose=Pose.at(10, 16)), peers[1])
    elif control == "shape":
        targets = (replace(target, base=OvalBase(1, 1)),)
    else:
        source = replace(
            source,
            body_parts=(ModelBodyPart("body", CircularBase(1), 1, 0, 0, 1, "constructed"),),
        )
    assert not endpoint_excluded_by_connected_components(
        source=source,
        peers=peers,
        goal=MovementGoal(models=targets, horizontal_inches=1),
        horizontal_inches=2,
    )


@pytest.mark.parametrize(
    "control", ["blocked", "clear", "raised", "remote-support", "tangent", "shape", "reachable"]
)
def test_connected_endpoint_overlap_requires_collision_and_support_proof(control: str) -> None:
    from warhammer40k_core.geometry.base import CircularBase, OvalBase
    from warhammer40k_core.geometry.connected_endpoint_proof import (
        endpoint_excluded_by_connected_components,
    )
    from warhammer40k_core.geometry.movement_reachability import MovementGoal
    from warhammer40k_core.geometry.terrain import TerrainVolume
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    source = Model("mover", Pose.at(5, 10), CircularBase(0.5), ModelVolume(1))
    lower = replace(source, model_id="lower", pose=Pose.at(10, 10))
    upper = replace(source, model_id="upper", pose=Pose.at(10, 13.2))
    target = replace(source, model_id="enemy", pose=Pose.at(10, 14.9))
    goal = MovementGoal(models=(target,), range_inches=1)
    terrain: tuple[TerrainVolume, ...] = ()
    blockers: tuple[Model, ...] = (upper,)
    if control == "clear":
        blockers = ()
    elif control == "raised":
        terrain = (TerrainVolume("support", Point3(10, 13, 0), 4, 4, 1.5),)
    elif control == "remote-support":
        terrain = (TerrainVolume("support", Point3(40, 35, 0), 4, 4, 1.5),)
    elif control == "tangent":
        target = replace(target, pose=Pose.at(10, 15))
        upper = replace(upper, pose=Pose.at(10, 14))
        goal = MovementGoal(models=(target,), range_inches=1)
        blockers = (upper,)
    elif control == "shape":
        source = replace(source, base=OvalBase(1, 1))
    elif control == "reachable":
        upper = replace(upper, pose=Pose.at(12.8, 11))
        blockers = (lower, upper)
    assert not endpoint_excluded_by_connected_components(
        source=source, peers=(lower, upper), goal=goal, horizontal_inches=2
    )
    assert endpoint_excluded_by_connected_components(
        source=source,
        peers=(lower, upper),
        goal=goal,
        horizontal_inches=2,
        blockers=blockers,
        terrain=terrain,
    ) is (control in {"blocked", "remote-support"})
    if control == "reachable":
        from tests.support.section01_geometry import witnessed_query
        from warhammer40k_core.geometry.movement_reachability import movement_reachability

        query = witnessed_query(source, Pose.at(10, 13), 10, goal, (target,))
        query = replace(
            query,
            coherent_models=(lower, upper),
            path_context=replace(query.path_context, friendly_models=blockers),
        )
        result = movement_reachability(query)
        assert result.reachable
        assert result.witness is not None
        assert replace(query.path_context, witness=result.witness).validate().is_valid
        assert replace(query.terrain_context, witness=result.witness).validate().is_valid


def test_shared_ordered_history_reader_preserves_existing_fight_witness(
    section11_definitions: Section02Definitions,
) -> None:
    from tests.support.section12_fixtures import (
        begin as begin_fight,
    )
    from tests.support.section12_fixtures import (
        checkpoint,
        engaged_case,
        paths,
        submit_move,
    )
    from tests.support.section12_fixtures import (
        session_for as fight_session,
    )
    from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
    from warhammer40k_core.engine.sequential_movement import complete_movement_witness

    state, unit, enemy = engaged_case(section11_definitions)
    checkpoint(state, FightPhaseStepKind.PILE_IN)
    session = fight_session(section11_definitions, state)
    begin_fight(session)
    witness = paths(state, (unit.unit_instance_id,), 0.5)
    status = submit_move(session, targets=(enemy.unit_instance_id,), witness=witness)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    controller = session.lifecycle.decision_controller
    event = next(
        e for e in controller.event_log.records if e.event_type == "fight_movement_completed"
    )
    assert isinstance(event.payload, dict)
    assert (
        complete_movement_witness(
            event=event,
            payload=event.payload,
            resolution=event.payload,
            decisions=tuple(controller.records),
        )
        == witness
    )


@pytest.mark.parametrize("proof", ["disjoint", "blocked"])
def test_connected_endpoint_certificate_survives_charge_history_reconstruction(
    section11_definitions: Section02Definitions,
    proof: str,
) -> None:
    from tests.setup_completion_helpers import record_current_battlefield_placements_for_fixture
    from tests.support.section00_fixtures import conversion_mission
    from warhammer40k_core.engine.charge_endpoint_history import validate_charge_endpoint_history
    from warhammer40k_core.engine.charge_model_endpoints import ChargeModelEndpointWitness
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState

    state, body, leader, enemy, formation = attached_case(
        section11_definitions, body_datasheet=SPAWN
    )
    # An explicitly custom empty battlefield is round-trip supported; the
    # clause-level fixture's stripped official layout is not a saved mission.
    state.mission_setup = conversion_mission()
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    state.starting_strength_records.sort(key=lambda r: r.unit_instance_id)
    far, near = body.own_model_ids()
    bridge = leader.own_model_ids()[0]
    poses = {
        far: Pose.at(5, 10),
        near: Pose.at(8, 10),
        bridge: Pose.at(11, 8.1),
        **{m: Pose.at(20, 10 + 2.5 * i) for i, m in enumerate(enemy.own_model_ids())},
    }
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    army,
                    unit_placements=tuple(
                        replace(
                            unit,
                            model_placements=tuple(
                                replace(model, pose=poses.get(model.model_instance_id, model.pose))
                                for model in unit.model_placements
                            ),
                        )
                        for unit in army.unit_placements
                    ),
                )
                for army in state.battlefield_state.placed_armies
            ),
        )
    )
    # Preserve a real rolled budget while arranging this constructed scene to
    # require a connectivity certificate for the middle model.
    probe = session_for(section11_definitions, deepcopy(state))
    assert probe.lifecycle.state is not None
    record_current_battlefield_placements_for_fixture(
        probe.lifecycle.state, decisions=probe.lifecycle.decision_controller
    )
    begin(probe)
    choose(probe, formation.attached_unit_instance_id)
    unmodified = roll(probe).value
    modifier(state, formation.attached_unit_instance_id, 10 - unmodified)
    session = session_for(section11_definitions, state)
    record_current_battlefield_placements_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    begin(session)
    choose(session, formation.attached_unit_instance_id)
    targets(session, (enemy.unit_instance_id,))
    assert roll(session).value == 10
    path = PathWitness.for_paths(
        (
            (near, (poses[near], Pose.at(17.3 if proof == "disjoint" else 17.5, 10))),
            (
                bridge,
                (poses[bridge], Pose.at(14.2, 8.1) if proof == "disjoint" else Pose.at(16.8, 8.25)),
            ),
            (far, (poses[far], Pose.at(11 if proof == "disjoint" else 13.5, 10))),
        )
    )
    if proof == "blocked":
        from tests.support.section03_fixtures import geometry
        from warhammer40k_core.geometry.connected_endpoint_proof import (
            endpoint_excluded_by_connected_components,
        )
        from warhammer40k_core.geometry.movement_reachability import MovementGoal

        source = geometry(leader, (poses[bridge],))[0]
        peers = geometry(
            body, tuple(path.final_pose_for_model(mid) for mid in body.own_model_ids())
        )
        goal = MovementGoal(
            models=geometry(enemy, tuple(poses[mid] for mid in enemy.own_model_ids()), enemy=True),
            range_inches=1,
        )
        assert not endpoint_excluded_by_connected_components(
            source=source, peers=peers, goal=goal, horizontal_inches=2
        )
        assert endpoint_excluded_by_connected_components(
            source=source,
            peers=peers,
            goal=goal,
            horizontal_inches=2,
            blockers=tuple(m for m in peers if m.model_id == near),
        )
    status = propose(session, formation.attached_unit_instance_id, (enemy.unit_instance_id,), path)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    event = events(session, "charge_move_completed")[-1]
    endpoint = event["endpoint_witness"]
    assert isinstance(endpoint, dict)
    rows = endpoint["model_endpoints"]
    assert isinstance(rows, list)
    row = next(r for r in rows if isinstance(r, dict) and r["model_instance_id"] == bridge)
    assert isinstance(row, dict)
    admitted = ChargeModelEndpointWitness.from_payload(row)
    evidence = (
        admitted.engagement_reachability if proof == "disjoint" else admitted.preferred_reachability
    )
    assert evidence.status == "endpoint_unreachable"
    assert evidence.alternative_witness is None
    # This already-permitted attached-unit kernel is not a mustered roster. Test
    # the real persistence owner's proof admission with independently decoded
    # state/events/decisions; do not claim whole-session or setup qualification.
    restored = GameState.from_payload(json.loads(json.dumps(state.to_payload())))
    controller = session.lifecycle.decision_controller
    validate_charge_endpoint_history(
        state=restored,
        event_records=tuple(
            EventRecord.from_payload(json.loads(json.dumps(record.to_payload())))
            for record in controller.event_log.records
        ),
        decision_records=tuple(
            DecisionRecord.from_payload(json.loads(json.dumps(record.to_payload())))
            for record in controller.records
        ),
        ability_index_for_player=session.lifecycle._charge_phase_handler.ability_index_for_player,  # pyright: ignore[reportPrivateUsage]
    )
    assert restored.to_payload() == state.to_payload()


def test_named_ruleset_charge_completion_survives_persistence() -> None:
    from tests.phase15a_charge_test_support import (
        _charge_lifecycle,
        _compact_test_unit_poses,
    )
    from tests.support.section11_fixtures import select
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.replay import ReplayRunner

    # The supported named descriptor has the same movement policies as the
    # mission-derived descriptor but a distinct configured version and hash.
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("charger", "spare"),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(10, 24), model_count=5),
        game_id="named-ruleset-charge-persistence",
    )
    session = LocalGameSession(lifecycle)
    state = lifecycle.state
    assert state is not None
    configured = lifecycle.config.ruleset_descriptor
    assert configured.descriptor_hash == state.ruleset_descriptor_hash
    assert configured.descriptor_hash != state.runtime_ruleset_descriptor().descriptor_hash
    assert configured.coherency_policy == state.runtime_ruleset_descriptor().coherency_policy
    unit, enemy = units["charger"], units["enemy"]
    select(session, unit)
    request = lifecycle.pending_decision_request()
    assert request is not None
    if request.decision_type == "select_dice_reroll":
        choose(session, "decline", result_id="named-charge:decline-reroll")
    targets(session, (enemy.unit_instance_id,))
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    path = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(
                        model.pose.position.x,
                        model.pose.position.y + 2.0,
                        model.pose.position.z,
                        facing_degrees=model.pose.facing.degrees,
                    ),
                ),
            )
            for model in reversed(placement.model_placements)
        )
    )
    status = propose(session, unit.unit_instance_id, (enemy.unit_instance_id,), path)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    event = events(session, "charge_move_completed")[-1]
    coherency = event["coherency_result"]
    assert isinstance(coherency, dict)
    assert coherency["ruleset_descriptor_hash"] == configured.descriptor_hash
    saved = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    replay = ReplayRunner.from_payload(saved["replay_artifact"]).run()
    assert replay.to_payload()["status"] == "reproduced"

    # The configured identity remains authoritative. Using the canonical policy
    # descriptor's different hash in an otherwise accepted event is still wrong.
    damaged = json.loads(json.dumps(lifecycle.to_payload()))
    completion = next(
        row
        for row in damaged["decisions"]["event_log"]
        if row["event_type"] == "charge_move_completed"
    )
    completion["payload"]["coherency_result"]["ruleset_descriptor_hash"] = (
        state.runtime_ruleset_descriptor().descriptor_hash
    )
    with pytest.raises(GameLifecycleError, match="coherency authority drifted"):
        GameLifecycle.from_payload(damaged)
