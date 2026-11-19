"""Small movement facade integration: no setup phases or game startup."""

from dataclasses import replace
from math import isclose

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import grid, native_state, paths, placement
from tests.support.section03_session import movement_session
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_budget_modifiers import model_movement_characteristic
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition


def _add_spare_mover(definitions: Section02Definitions, state: GameState) -> None:
    # A second eligible native unit keeps the facade at this movement boundary.
    spare = definitions.unit(CHAOS_SPAWN, identity="spare")
    owner = next(a for a in state.army_definitions if a.player_id == "owner")
    state.army_definitions = [
        replace(a, units=(*a.units, spare)) if a == owner else a for a in state.army_definitions
    ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a, unit_placements=(*a.unit_placements, placement(spare, grid(spare, 10, 25)))
                )
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )


@pytest.mark.parametrize("action", ["normal_move", "fall_back"])
def test_native_facade_rejects_swap_then_applies_legal_witness(
    section03_definitions: Section02Definitions, section03_setup_mission: MissionSetup, action: str
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    state = native_state(
        section03_definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(10, 13.8), Pose.at(12.5, 13.8)) if action == "fall_back" else None,
    )
    state.mission_setup = section03_setup_mission
    _add_spare_mover(section03_definitions, state)
    handler = MovementPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
    )
    session = movement_session(section03_definitions, state)
    lifecycle = session.lifecycle
    status = handler.begin_phase(state=state, decisions=lifecycle.decision_controller)
    request = status.decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id, option_id=unit.unit_instance_id, result_id="select"
    )
    request = status.decision_request
    assert request is not None
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict)
        and o.payload.get("movement_phase_action") == action
        and o.payload.get("fall_back_mode", "ordered_retreat") == "ordered_retreat"
    )
    assert isinstance(option.payload, dict)
    movement_mode = option.payload["movement_mode"]
    assert isinstance(movement_mode, str)
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="action"
    )
    request = status.decision_request
    assert request is not None
    before = state.battlefield_state
    legal = (
        (Pose.at(10, 6), Pose.at(12.5, 6))
        if action == "fall_back"
        else (Pose.at(10, 11), Pose.at(12.5, 11))
    )
    for index, ends in enumerate((tuple(reversed(starts)), legal)):
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"path-{index}",
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=unit.unit_instance_id,
                    movement_phase_action=action,
                    movement_mode=movement_mode,
                    fall_back_mode="ordered_retreat" if action == "fall_back" else None,
                    witness=paths(unit, starts, ends),
                ).to_payload()
            ),
        )
        if index == 0:
            assert status.status_kind is LifecycleStatusKind.INVALID
            assert state.battlefield_state == before
            request = lifecycle.decision_controller.queue.pending_requests[0]
        else:
            assert status.status_kind is not LifecycleStatusKind.INVALID
            assert state.battlefield_state is not None
            assert (
                tuple(
                    p.pose
                    for p in state.battlefield_state.unit_placement_by_id(
                        unit.unit_instance_id
                    ).model_placements
                )
                == ends
            )
    assert len(lifecycle.decision_controller.records) == 4
    assert state.movement_phase_state is not None
    assert unit.unit_instance_id in state.movement_phase_state.moved_unit_ids
    if action == "fall_back":
        # The selected move's After Moving restrictions exist when activation ends.
        restriction = next(
            r for r in state.fell_back_unit_states if r.unit_instance_id == unit.unit_instance_id
        )
        assert not restriction.can_shoot
        assert not restriction.can_declare_charge
        assert restriction.cleanup_point == "end_of_turn"


@pytest.mark.parametrize(
    ("offset", "rounded_offset", "blocked", "violation"),
    [
        (0.00049, 0.0, False, None),
        (-0.9375, -0.937, False, None),
        (0.00051, 0.001, False, "movement_distance_exceeded"),
        (0.00049, 0.0, True, "terrain_feature_transit_forbidden"),
    ],
    ids=("below-budget-midpoint", "exact-midpoint", "above-budget-midpoint", "blocked"),
)
def test_normal_move_facade_budgets_once_rounded_complete_paths(
    section03_definitions: Section02Definitions,
    section03_setup_mission: MissionSetup,
    offset: float,
    rounded_offset: float,
    blocked: bool,
    violation: str | None,
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    budget = model_movement_characteristic(unit.own_models[0]).final
    starts = (Pose.at(10, 10), Pose.at(10, 13))
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    state = native_state(section03_definitions, unit, starts, enemy=enemy)
    state.mission_setup = section03_setup_mission
    _add_spare_mover(section03_definitions, state)
    assert state.battlefield_state is not None
    if blocked:
        display = TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=13,
            center_y_inches=10,
            width_inches=2,
            depth_inches=2,
            display_template_id=None,
        )
        wall = TerrainFeatureDefinition(
            "budget-obstruction",
            TerrainFeatureKind.SEALED_BUILDINGS,
            13,
            10,
            2,
            2,
            display.footprint_polygon,
            display,
            walls=(TerrainWallDefinition("wall", 13, 10, 0, 0.5, 2, 5),),
        )
        state.mission_setup = replace(section03_setup_mission, terrain_features=(wall,))
        state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(wall,)))
    before = state.battlefield_state
    session = movement_session(section03_definitions, state)
    lifecycle = session.lifecycle
    handler = MovementPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
    )
    request = handler.begin_phase(
        state=state, decisions=lifecycle.decision_controller
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=unit.unit_instance_id, result_id="budget-unit"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id="normal_move", result_id="budget-action"
    ).decision_request
    assert request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    travel = budget + offset
    ends = tuple(Pose.at(10 + travel, start.position.y, facing_degrees=12.125) for start in starts)
    witness = PathWitness.for_paths(
        tuple(
            (model_id, (start, Pose.at(10 + travel / 2, start.position.y), end))
            for model_id, start, end in zip(unit.own_model_ids(), starts, ends, strict=True)
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="budget-path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode="normal",
                witness=witness,
            ).to_payload()
        ),
    )
    assert state.battlefield_state is not None
    if violation is not None:
        assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
        assert isinstance(status.payload, dict)
        assert status.payload["violation_code"] == violation, status.to_payload()
        assert state.battlefield_state == before
    else:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        placement_after = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        assert tuple(model.pose for model in placement_after.model_placements) == ends
        completed = next(
            event.payload
            for event in lifecycle.decision_controller.event_log.records
            if event.event_type == "movement_activation_completed"
        )
        assert isinstance(completed, dict)
        results = completed["path_validation_results"]
        assert isinstance(results, list)
        assert len(results) == len(unit.own_models)
        for result in results:
            assert isinstance(result, dict)
            distance = result["movement_distance_witness"]
            assert isinstance(distance, dict)
            consumed = distance["budget"]
            assert isinstance(consumed, dict)
            total = consumed["total_distance_inches"]
            raw_total = consumed["straight_line_distance_inches"]
            assert type(total) is float
            assert type(raw_total) is float
            assert isclose(total, budget + rounded_offset, rel_tol=0, abs_tol=1e-12)
            assert isclose(raw_total, travel, rel_tol=0, abs_tol=1e-12)
