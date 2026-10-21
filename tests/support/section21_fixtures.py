"""Section21 native physical kernels; explicit source grants, no roster claim."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, paths, placement, scenario
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementHandler,
    TriggeredMovementKind,
    TriggeredMovementResolution,
)
from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

LORD = "000004078"
SPAWN = "000004090"
SERPENT = "000000599"
BODY = "000004080"
IDS = (LORD, SPAWN, SERPENT, BODY)


@pytest.fixture(scope="session")
def section21_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    digest = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    seconds = perf_counter() - start
    print(f"Section21 preparation {seconds:.6f}s; four indexed native definitions")
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == digest
    )


@dataclass
class SurgeScene:
    definitions: Section02Definitions
    state: GameState
    unit: UnitInstance
    target: UnitInstance
    starts: tuple[Pose, ...]

    def session(self) -> LocalGameSession:
        attach_mission(self.state)
        add_unit(self.state, self.definitions.unit(LORD, identity="spare"), (Pose.at(10, 35),))
        config = movement_session(self.definitions, self.state).lifecycle.config
        shooting = ShootingPhaseHandler(
            ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
        )
        flow = BattleRoundFlow(
            phase_handlers={BattlePhase.SHOOTING: shooting},
            ruleset_descriptor=config.ruleset_descriptor,
            army_catalog=config.army_catalog,
        )
        return LocalGameSession(
            GameLifecycle(
                state=self.state,
                _config=config,
                _movement_phase_handler=MovementPhaseHandler(
                    ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
                ),
                _triggered_movement_handler=TriggeredMovementHandler(
                    ruleset_descriptor=config.ruleset_descriptor
                ),
                _shooting_phase_handler=shooting,
                _battle_round_flow=flow,
            )
        )


def surge_scene(d: Section02Definitions, *, multi: bool = False, gap: float = 8) -> SurgeScene:
    sheet = SPAWN if multi else LORD
    unit = d.unit(sheet)
    target = d.unit(sheet, identity="target", army_id="enemy")
    starts = tuple(Pose.at(10, 10 + 2.5 * i) for i in range(len(unit.own_models)))
    own = geometry(unit, starts)[0]
    other = geometry(target, starts, enemy=True)[0]
    assert isinstance(own.base, CircularBase)
    assert isinstance(other.base, CircularBase)
    x = 10 + own.base.radius + other.base.radius + gap
    state = native_state(
        d, unit, starts, enemy=target, enemy_poses=tuple(Pose.at(x, p.position.y) for p in starts)
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    return SurgeScene(d, state, unit, target, starts)


def enemy_at(s: SurgeScene, identity: str, poses: tuple[Pose, ...]) -> UnitInstance:
    unit = s.definitions.unit(LORD, identity=identity, army_id="enemy")
    s.state.army_definitions[:] = [
        replace(a, units=(*a.units, unit)) if a.player_id == "opponent" else a
        for a in s.state.army_definitions
    ]
    s.state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="opponent", unit=unit)
    )
    assert s.state.battlefield_state is not None
    s.state.replace_battlefield_state(
        replace(
            s.state.battlefield_state,
            placed_armies=tuple(
                replace(a, unit_placements=(*a.unit_placements, placement(unit, poses, enemy=True)))
                if a.player_id == "opponent"
                else a
                for a in s.state.battlefield_state.placed_armies
            ),
        )
    )
    return unit


def descriptor(
    s: SurgeScene, *, maximum: float = 4, event_id: str = "s21:grant"
) -> TriggeredMovementDescriptor:
    return TriggeredMovementDescriptor(
        TriggeredMovementKind.SURGE,
        "constructed:s21:surge-grant",
        ReactionWindow(
            phase=BattlePhase.SHOOTING,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="just_after_enemy_unit_has_shot",
            source_event_id=event_id,
        ),
        maximum,
    )


def surge_path(s: SurgeScene, distances: tuple[float, ...]) -> PathWitness:
    return paths(
        s.unit,
        s.starts,
        tuple(
            Pose.at(p.position.x + distance, p.position.y)
            for p, distance in zip(s.starts, distances, strict=True)
        ),
    )


def surge_result(
    s: SurgeScene, path: PathWitness, *, maximum: float = 4, target_id: str | None = None
) -> TriggeredMovementResolution:
    board = scenario(s.state)
    return resolve_triggered_movement(
        scenario=board,
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(s.unit.unit_instance_id),
        descriptor=descriptor(s, maximum=maximum),
        path_witness=path,
        battle_round=s.state.battle_round,
        turn_player_id="owner",
        battle_shocked_unit_ids=tuple(s.state.battle_shocked_unit_ids),
        surge_target_unit_instance_id=s.target.unit_instance_id if target_id is None else target_id,
    )


def offer_surge(
    session: LocalGameSession,
    s: SurgeScene,
    *,
    maximum: float = 4,
    kind: TriggeredMovementKind = TriggeredMovementKind.SURGE,
) -> DecisionRequest:
    event = session.lifecycle.decision_controller.event_log.append(
        "source_rule_triggered",
        {
            "game_id": s.state.game_id,
            "battle_round": s.state.battle_round,
            "phase": "shooting",
            "active_player_id": s.state.active_player_id,
            "source_rule_id": "constructed:s21:surge-grant",
        },
    )
    desc = replace(descriptor(s, maximum=maximum, event_id=event.event_id), movement_kind=kind)
    request = triggered_movement_unit_selection_request(
        state=s.state,
        decisions=session.lifecycle.decision_controller,
        player_id="owner",
        descriptor=desc,
        eligible_units=(
            TriggeredMovementEligibleUnit(
                s.unit.unit_instance_id, "constructed:s21:hook", desc.source_rule_id
            ),
        ),
    )
    session.lifecycle.decision_controller.request_decision(request)
    return request


def submit_surge(
    session: LocalGameSession,
    request: DecisionRequest,
    path: PathWitness,
    *,
    result_id: str = "s21:path",
) -> LifecycleStatus:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action="surge_move",
                witness=path,
            ).to_payload()
        ),
    )
