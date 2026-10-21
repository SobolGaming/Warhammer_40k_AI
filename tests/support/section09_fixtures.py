"""Section09 boundary kernels: indexed native definitions, fresh mutable graphs.

No roster admission, prior-phase traversal or faction grant is implied. A spare
unit keeps single-activation tests inside Movement without mission orchestration.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from functools import cache
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state, paths, placement
from tests.support.section03_session import movement_session
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    is_mortal_wound_resolution_request,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose

IDS = ("000004080", "000004090", "000000968", "000004078", "000000599", "000000969", "000001114")


def finish_hazard_choices(session: LocalGameSession, status: LifecycleStatus) -> LifecycleStatus:
    """Select through the native shared mortal-wound request, without changing dice."""
    if status.decision_request is not None and is_mortal_wound_resolution_request(
        status.decision_request
    ):
        anchor_hazard_scene(session)
    count = 0
    while status.decision_request is not None and is_mortal_wound_resolution_request(
        status.decision_request
    ):
        request = status.decision_request
        count += 1
        assert count <= 30
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"hazard-choice-{count}",
        )
    return status


@pytest.fixture(scope="session")
def section09_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    mission = movement_mission()
    mission_before = mission.to_payload()
    seconds = perf_counter() - start
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    print(f"Section09 definition preparation: {seconds:.6f}s; {len(IDS)} native definitions")
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )
    assert mission.to_payload() == mission_before


def movement_case(
    definitions: Section02Definitions,
    *,
    datasheet: str = "000004090",
    engaged: bool = False,
    location: str = "battlefield",
    spare: bool = True,
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    unit = definitions.unit(datasheet)
    starts = grid(unit)
    enemy = definitions.unit("000004090", army_id="enemy", identity="enemy")
    state = native_state(
        definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(10, 13.8), Pose.at(12.5, 13.8)) if engaged else None,
    )
    attach_mission(state)
    if spare:
        add_unit(
            state,
            definitions.unit("000004090", identity="spare"),
            (Pose.at(10, 30), Pose.at(12.5, 30)),
        )
    if location == "reserves":
        reserve_unit(state, unit)
        assert state.battlefield_state is not None
        state.replace_battlefield_state(unplace(state, unit))
    elif location == "embarked":
        from warhammer40k_core.engine.transports import (
            TransportCapacityProfile,
            TransportCargoState,
        )

        transport = definitions.unit("000000599", identity="transport")
        add_unit(state, transport, grid(transport, 20, 20))
        assert state.battlefield_state is not None
        state.replace_battlefield_state(unplace(state, unit))
        # Explicit Core cargo boundary contract; no cross-faction embark admission claim.
        state.transport_cargo_states.append(
            TransportCargoState(
                "owner",
                transport.unit_instance_id,
                TransportCapacityProfile(
                    transport.datasheet_id, 12, source_id="constructed:section09:cargo"
                ),
                (unit.unit_instance_id,),
            )
        )
    else:
        assert location == "battlefield"
    return movement_session(definitions, state), state, unit


def attach_mission(state: GameState) -> None:
    state.mission_setup = movement_mission()
    state.army_definitions[:] = sorted(
        (
            replace(
                army,
                force_disposition_id=state.mission_setup.primary_mission_assignment_for_player(
                    army.player_id
                ).force_disposition_id,
            )
            for army in state.army_definitions
        ),
        key=lambda army: army.army_id,
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            battlefield_width_inches=state.mission_setup.battlefield_width_inches,
            battlefield_depth_inches=state.mission_setup.battlefield_depth_inches,
        )
    )


@cache
def movement_mission() -> MissionSetup:
    # Physical proposal context requires source mission geometry even when no
    # mission scoring or prior phases are exercised. Reuse one immutable object.
    from warhammer40k_core.rules.mission_pack_import import (
        warhammer_event_companion_2026_07_mission_pack,
    )

    return replace(
        MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-2",
            terrain_layout_id="disruption-vs-reconnaissance-layout-2",
            attacker_player_id="owner",
            defender_player_id="opponent",
            attacker_force_disposition_id="disruption",
            defender_force_disposition_id="reconnaissance",
        ),
        battlefield_layout_id=None,
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
    )


def unplace(state: GameState, unit: UnitInstance) -> BattlefieldRuntimeState:
    assert state.battlefield_state is not None
    return replace(
        state.battlefield_state,
        placed_armies=tuple(
            replace(
                a,
                unit_placements=tuple(
                    p for p in a.unit_placements if p.unit_instance_id != unit.unit_instance_id
                ),
            )
            for a in state.battlefield_state.placed_armies
        ),
    )


def add_unit(state: GameState, unit: UnitInstance, poses: tuple[Pose, ...]) -> None:
    state.army_definitions[:] = [
        replace(a, units=(*a.units, unit)) if a.player_id == "owner" else a
        for a in state.army_definitions
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="owner", unit=unit)
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(a, unit_placements=(*a.unit_placements, placement(unit, poses)))
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )


def begin(session: LocalGameSession) -> DecisionRequest:
    state = session.lifecycle.state
    assert state is not None
    status = MovementPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=session.lifecycle.config.army_catalog,
    ).begin_phase(state=state, decisions=session.lifecycle.decision_controller)
    assert status.decision_request is not None
    return status.decision_request


def select(session: LocalGameSession, unit: UnitInstance) -> DecisionRequest:
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, option_id=unit.unit_instance_id, result_id="select"
    )
    assert status.decision_request is not None
    return status.decision_request


def choose(session: LocalGameSession, request: DecisionRequest, option: str) -> DecisionRequest:
    status = session.submit_option(
        request_id=request.request_id, option_id=option, result_id="action"
    )
    assert status.decision_request is not None
    return status.decision_request


def propose(
    session: LocalGameSession,
    request: DecisionRequest,
    unit: UnitInstance,
    ends: tuple[Pose, ...],
    *,
    result_id: str = "path",
) -> LifecycleStatus:
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert context.context is not None
    action = context.movement_phase_action
    mode = context.context["movement_mode"]
    fall_back = context.context.get("fall_back_mode")
    assert isinstance(action, str)
    assert isinstance(mode, str)
    assert fall_back is None or isinstance(fall_back, str)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    starts = tuple(
        p.pose
        for p in state.battlefield_state.unit_placement_by_id(
            unit.unit_instance_id
        ).model_placements
    )
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action=action,
                movement_mode=mode,
                fall_back_mode=fall_back,
                witness=paths(unit, starts, ends),
            ).to_payload()
        ),
    )


def events(session: LocalGameSession, kind: str) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for event in session.lifecycle.decision_controller.event_log.records:
        if event.event_type == kind:
            assert isinstance(event.payload, dict)
            result.append(event.payload)
    return result


def anchor_hazard_scene(session: LocalGameSession) -> None:
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        record_primary_mission_boundary_checkpoint,
    )

    state = session.lifecycle.state
    assert state is not None
    assert state.active_player_id is not None
    # This kernel begins already placed. Supply the exact initial physical
    # history that full native setup supplies before damage followed by a move.
    record_primary_mission_boundary_checkpoint(
        state=state,
        event_log=session.lifecycle.decision_controller.event_log,
        boundary_kind="action_request",
        player_id=state.active_player_id,
        runtime_modifier_registry=session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry,  # pyright: ignore[reportPrivateUsage]
    )
