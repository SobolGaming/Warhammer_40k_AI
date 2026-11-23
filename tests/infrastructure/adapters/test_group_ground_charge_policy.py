from __future__ import annotations

import json
import multiprocessing
from dataclasses import replace
from functools import partial

import pytest

from tests import phase15a_charge_declaration_helpers as charge_fixtures
from tests.charge_distance_helpers import add_modifier, select_source, select_targets
from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.phase15a_charge_declaration_helpers import (
    charge_lifecycle,
    compact_test_unit_poses,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai import ground_charge_candidates, ground_charge_policy
from warhammer40k_core.ai.ground_charge_candidates import (
    ChargeSearchStop,
    GroundChargeCandidates,
    GroundChargeExhaustedError,
    generate_ground_charge_candidates,
)
from warhammer40k_core.ai.ground_charge_policy import prepare_ground_charge_policy
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyError,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.missions import mission_pack_for_id
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import rules_unit_id_for_unit_id
from warhammer40k_core.geometry.base import BaseShape
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.polygons import Point2D
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.shapely_backend import (
    FootprintGeometry,
    footprint_for_base,
    footprint_for_polygon_union,
)

ACTOR = "player-a"
TARGET = "army-beta:enemy"


@pytest.fixture
def group_charge() -> LocalGameSession:
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        game_id="five-ground-charge",
    )
    return _select_target(lifecycle, TARGET)


def _select_target(lifecycle: GameLifecycle, target: str) -> LocalGameSession:
    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="fixture", kind="modify_dice_roll", delta=10)
    session = LocalGameSession(lifecycle)
    request = select_targets(session, select_source(session), (target,))
    assert request.decision_type == "submit_movement_proposal"
    return session


def test_group_charge_generates_distinct_complete_witnesses(group_charge: LocalGameSession) -> None:
    view = group_charge.view(viewer_player_id=ACTOR)
    context = PlayerDecisionContext.from_view(view, choice_seed=1)
    generated = generate_ground_charge_candidates(context, raw_limit=4)
    assert generated == generate_ground_charge_candidates(
        PlayerDecisionContext.from_view(view, choice_seed=2), raw_limit=4
    )
    assert generated.stop is ChargeSearchStop.RAW_LIMIT
    source = view["unit_display_by_id"]["army-alpha:source"]
    endpoints: set[tuple[Pose, ...]] = set()
    for candidate in generated.candidates:
        assert candidate.action.proposal_json is not None
        action = json.loads(candidate.action.proposal_json)
        assert action["charge_target_unit_instance_ids"] == [TARGET]
        witness = PathWitness.from_payload(action["witness"])
        assert set(witness.model_ids()) == set(source["model_instance_ids"])
        endpoints.add(tuple(poses[-1] for _, poses in witness.model_paths))
    assert len(endpoints) == 4

    with pytest.raises(GroundChargeExhaustedError) as caught:
        generate_ground_charge_candidates(context, geometry_limit=1)
    assert caught.value.reason is ChargeSearchStop.GEOMETRY_LIMIT
    assert caught.value.counts.geometry_work == 1


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
def test_group_charge_commits_a_native_accept(group_charge: LocalGameSession) -> None:
    session = group_charge
    context = PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)
    before = payload_digest(session.lifecycle.to_payload())
    prepared = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=2)
    assert payload_digest(session.lifecycle.to_payload()) == before
    assert prepared.counts.accepted == 2
    assert prepared.counts.timed_out == 0

    registration = PolicyRouter((prepared.registration,)).resolve(context.route)
    action = registration.policy.choose(context)
    assert action.proposal_json is not None
    assert payload_digest(action.proposal_json) == prepared.ranked_accepted_ids[0]
    result = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        result_id="group-charge",
        payload=json.loads(action.proposal_json),
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        sum(
            event.event_type == "charge_move_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )


@pytest.fixture(scope="module")
def objective_charge() -> LocalGameSession:
    setup = charge_fixtures.mission_setup()
    mission = MissionSetup.from_mission_pack(
        mission_pack=mission_pack_for_id(setup.mission_pack_id),
        mission_pool_entry_id=setup.mission_pool_entry_id,
        attacker_player_id=setup.attacker_player_id,
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id=setup.defender_player_id,
        defender_force_disposition_id="purge-the-foe",
    )
    config = charge_fixtures.charge_config(
        game_id="objective-ground-charge", alpha_unit_ids=("source",), enemy_unit_ids=("enemy",)
    )
    configured = replace(
        config,
        mission_setup=mission,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids
        ),
    )

    def configured_charge(**kwargs: object) -> GameConfig:
        assert kwargs["game_id"] == configured.game_id
        return configured

    with pytest.MonkeyPatch.context() as fixture:
        fixture.setattr(charge_fixtures, "charge_config", configured_charge)
        fixture.setattr(
            charge_fixtures,
            "create_deterministic_battlefield_scenario",
            partial(
                create_deterministic_battlefield_scenario,
                terrain_features=mission.terrain_features,
            ),
        )
        lifecycle, _ = charge_lifecycle(
            game_id="objective-ground-charge",
            alpha_unit_ids=("source",),
            alpha_origins={"source": Pose.at(18, 32)},
            enemy_model_poses=compact_test_unit_poses(origin=Pose.at(18, 27.5), model_count=5),
        )
    return _select_target(lifecycle, TARGET)


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
def test_group_charge_accepts_attached_target_with_four_surviving_bodyguards() -> None:
    lifecycle, units = charge_lifecycle(
        game_id="attached-ground-charge",
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy", "leader"),
        enemy_attached_unit_ids=("enemy", "leader"),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        enemy_origins={"leader": Pose.at(17.3, 26)},
    )
    state = lifecycle.state
    assert state is not None
    destroy_rule_model_for_fixture(
        state=state,
        decisions=lifecycle.decision_controller,
        model_id=units["enemy"].own_models[-1].model_instance_id,
        destroying_player_id=ACTOR,
        source_unit_id=None,
        source_model_id=None,
    )
    target = rules_unit_id_for_unit_id(
        armies=tuple(state.army_definitions), unit_instance_id=TARGET
    )
    assert target != TARGET
    session = _select_target(lifecycle, target)
    view = session.view(viewer_player_id=ACTOR)
    battlefield = view["battlefield_view"]
    assert battlefield is not None
    members = [
        entity
        for entity in battlefield["authoritative"]["models_by_id"].values()
        if entity["rules_unit_instance_id"] == target and entity["state"] == "placed"
    ]
    assert len(members) == 5
    assert sum(entity["unit_instance_id"] == TARGET for entity in members) == 4
    assert (
        sum(entity["unit_instance_id"] == units["leader"].unit_instance_id for entity in members)
        == 1
    )

    context = PlayerDecisionContext.from_view(view, choice_seed=0)
    prepared = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=1)
    assert prepared.counts.accepted == 1
    action = prepared.registration.policy.choose(context)
    assert action.proposal_json is not None
    payload = json.loads(action.proposal_json)
    assert payload["charge_target_unit_instance_ids"] == [target]
    result = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        result_id="group-charge-attached",
        payload=payload,
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert any(
        event.event_type == "charge_move_completed"
        for event in session.lifecycle.decision_controller.event_log.records
    )


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
@pytest.mark.parametrize("limit", [0, 1, 1000])
def test_group_charge_objective_preprocessing_exhausts_before_geometry(
    objective_charge: LocalGameSession, monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    session = objective_charge
    context = PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)
    snapshot = session.lifecycle.to_payload()
    assert session.lifecycle.pending_decision_request() is not None
    calls: list[str] = []

    def footprint(polygons: tuple[tuple[Point2D, ...], ...]) -> FootprintGeometry:
        calls.append("objective polygon")
        return footprint_for_polygon_union(polygons)

    def model_footprint(base: BaseShape, pose: Pose) -> FootprintGeometry:
        calls.append("model footprint")
        return footprint_for_base(base, pose)

    monkeypatch.setattr(ground_charge_candidates, "footprint_for_polygon_union", footprint)
    monkeypatch.setattr(ground_charge_candidates, "footprint_for_base", model_footprint)
    with pytest.raises(GroundChargeExhaustedError) as caught:
        prepare_ground_charge_policy(session, context, geometry_limit=limit)
    assert caught.value.reason is ChargeSearchStop.GEOMETRY_LIMIT
    assert caught.value.counts.geometry_work == limit
    assert caught.value.counts.raw == 0
    assert caught.value.counts.accepted == 0
    assert not calls
    assert session.lifecycle.to_payload() == snapshot


@pytest.mark.parametrize("oversized", ["areas", "vertices", "linked-vertices"])
def test_group_charge_objective_inventory_limits(
    objective_charge: LocalGameSession, oversized: str
) -> None:
    view = objective_charge.view(viewer_player_id=ACTOR)
    mission = view["mission_setup"]
    assert isinstance(mission, dict)
    areas = mission["terrain_areas"]
    definitions = mission["objective_terrain_areas"]
    assert isinstance(areas, list)
    assert isinstance(definitions, list)
    terrain = areas[0]
    assert isinstance(terrain, dict)
    points = terrain["footprint_polygon"]
    assert isinstance(points, list)
    if oversized == "areas":
        mission["terrain_areas"] = areas[:1] * 257
    elif oversized == "vertices":
        terrain["footprint_polygon"] = points[:4] * 65
    else:
        definition = definitions[0]
        assert isinstance(definition, dict)
        terrain["footprint_polygon"] = points[:4] * 64
        definition["terrain_area_ids"] = [terrain["terrain_area_id"]]
        mission["terrain_areas"] = areas[:1]
        mission["objective_terrain_areas"] = definitions[:1] * 17
    context = PlayerDecisionContext.from_view(view, choice_seed=0)
    with pytest.raises(PolicyError, match="objective inventory"):
        generate_ground_charge_candidates(context)


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
def test_group_charge_ranks_objective_reach_ahead_of_shorter_accepted_travel(
    objective_charge: LocalGameSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = objective_charge
    context = PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=0)
    generated = generate_ground_charge_candidates(context)
    short = min(
        (candidate for candidate in generated.candidates if candidate.objective_reach == 0),
        key=lambda candidate: (candidate.longest_path_inches, candidate.total_path_inches),
    )
    longer = next(
        candidate
        for candidate in generated.candidates
        if candidate.objective_reach > 0
        and candidate.longest_path_inches > short.longest_path_inches
    )

    def travel_first(*_args: object, **_kwargs: object) -> GroundChargeCandidates:
        return GroundChargeCandidates((short, longer), generated.geometry_work, generated.stop)

    # Validate the exact two proposals from the real generator in travel-first order.
    monkeypatch.setattr(ground_charge_policy, "generate_ground_charge_candidates", travel_first)
    prepared = prepare_ground_charge_policy(session, context, accepted_limit=2)
    assert prepared.counts.accepted == 2
    assert [probe.candidate_id for probe in prepared.validations] == [
        short.candidate_id,
        longer.candidate_id,
    ]
    assert prepared.ranked_accepted_ids == (longer.candidate_id, short.candidate_id)
    assert prepared.registration.policy.choose(context) == longer.action
