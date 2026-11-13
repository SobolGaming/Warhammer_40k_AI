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
from warhammer40k_core.geometry.pose import Pose


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


def test_connected_endpoint_certificate_survives_charge_history_reconstruction(
    section11_definitions: Section02Definitions,
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
            (near, (poses[near], Pose.at(17.3, 10))),
            (bridge, (poses[bridge], Pose.at(14.2, 8.1))),
            (far, (poses[far], Pose.at(11, 10))),
        )
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
    assert admitted.engagement_reachability.status == "endpoint_unreachable"
    assert admitted.engagement_reachability.alternative_witness is None
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
