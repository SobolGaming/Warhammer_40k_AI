"""Selected native definitions and fresh Section20 boundary kernels.

Core declarations/permissions, prices and optional keyword contracts are explicit
premises. They certify neither complete roster nor named provider admission.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, placement
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission, begin, unplace
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.reserves import ReserveUnitPointValue
from warhammer40k_core.engine.triggered_movement import TriggeredMovementHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

BODY = "000004080"
LORD = "000004078"
YRIEL = "000004193"
WAVE = "000000599"
SPAWN = "000004090"
AVENGERS = "000000593"
IDS = (BODY, LORD, YRIEL, WAVE, SPAWN, AVENGERS)


@pytest.fixture(scope="session")
def section20_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    elapsed = perf_counter() - start
    print(f"Section20 preparation: {elapsed:.6f}s; six native selected definitions")
    yield Section02Definitions(package, elapsed)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


@dataclass
class ReserveScene:
    definitions: Section02Definitions
    state: GameState
    unit: UnitInstance
    enemy: UnitInstance

    def session(self) -> LocalGameSession:
        attach_mission(self.state)
        return section20_session(self.definitions, self.state)


def section20_session(
    d: Section02Definitions,
    state: GameState,
    *,
    reserve_points: tuple[ReserveUnitPointValue, ...] = (),
) -> LocalGameSession:
    if state.mission_setup is not None:
        # The inherited geometry-only fixture deliberately omits the official
        # layout. Give this custom empty terrain its own identities; preserve
        # the original fixture and its Q18-01 qualification unchanged.
        state.mission_setup = replace(
            state.mission_setup,
            deployment_map_id="constructed:s20:deployment",
            terrain_layout_id="constructed:s20:terrain",
            battlefield_regions=(),
        )
        from warhammer40k_core.engine.reserve_arrival_requirements import (
            reposition_destruction_policy,
        )

        policy = reposition_destruction_policy(
            mission_setup=state.mission_setup, destruction_deadline_policy=None
        )
        state.reserve_states[:] = [
            replace(r, destruction_deadline_policy=policy) for r in state.reserve_states
        ]
    config = movement_session(d, state).lifecycle.config
    if reserve_points:
        config = replace(config, reserve_unit_points=reserve_points)
    state.ruleset_descriptor_hash = config.ruleset_descriptor.descriptor_hash
    state.rules_overlay_ids = config.ruleset_descriptor.rules_overlay_ids
    session = LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _movement_phase_handler=MovementPhaseHandler(
                ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
            ),
            _triggered_movement_handler=TriggeredMovementHandler(
                ruleset_descriptor=config.ruleset_descriptor
            ),
        )
    )
    for reserve in state.reserve_states:
        if reserve.declared_during_step is not None:
            session.lifecycle.decision_controller.event_log.append(
                "reserve_unit_declared",
                {
                    "game_id": state.game_id,
                    "player_id": reserve.player_id,
                    "unit_instance_id": reserve.unit_instance_id,
                    "reserve_state": validate_json_value(reserve.to_payload()),
                },
            )
    return session


def reserve_scene(d: Section02Definitions, *, sheet: str = YRIEL) -> ReserveScene:
    unit = d.unit(sheet)
    enemy = d.unit(LORD, identity="enemy", army_id="enemy")
    state = native_state(d, unit, enemy=enemy, enemy_poses=(Pose.at(35, 20),))
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(10, 35),))
    state.replace_battlefield_state(unplace(state, unit))
    state.battle_round = 2
    reserve_unit(state, unit)
    return ReserveScene(d, state, unit, enemy)


def ingress_request(session: LocalGameSession, unit: UnitInstance) -> DecisionRequest:
    begin(session)
    status = session.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    request = status.decision_request
    status = session.submit_option(
        request_id=request.request_id, result_id="s20:select", option_id=unit.unit_instance_id
    )
    assert status.decision_request is not None, status.to_payload()
    status = session.submit_option(
        request_id=status.decision_request.request_id, result_id="s20:ingress", option_id="ingress"
    )
    assert status.decision_request is not None, status.to_payload()
    return status.decision_request


def submit_ingress(
    session: LocalGameSession,
    request: DecisionRequest,
    unit: UnitInstance,
    poses: tuple[Pose, ...],
    *,
    result_id: str = "s20:placed",
) -> LifecycleStatus:
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_placement=placement(unit, poses),
            ).to_payload()
        ),
    )
