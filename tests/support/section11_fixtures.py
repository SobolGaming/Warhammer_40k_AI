"""Constructed Charge boundaries: indexed native definitions; fresh mutable state.

No setup, roster admission, preceding phases or full replay is implied. Mission
metadata is required by the physical proposal context, not played as a mission.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import cast

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, placement, scenario
from tests.support.section03_session import movement_session
from tests.support.section04_fixtures import pending
from tests.support.section09_fixtures import add_unit, attach_mission
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import (
    ChargeMoveProposal,
    ChargeMoveResolution,
    ChargePhaseHandler,
    resolve_charge_move,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

LORD = "000004078"
SPAWN = "000004090"
SERPENT = "000000599"
WRAITHLORD = "000000613"
IDS = (LORD, SPAWN, SERPENT, WRAITHLORD, "000004080")


@pytest.fixture(scope="session")
def section11_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    from tests.support.section09_fixtures import movement_mission

    mission = movement_mission()
    mission_before = mission.to_payload()
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    seconds = perf_counter() - start
    print(
        f"Section11 definition/mission preparation: {seconds:.6f}s; {len(IDS)} native definitions"
    )
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )
    assert mission.to_payload() == mission_before


def state_case(
    definitions: Section02Definitions,
    *,
    gap: float = 5,
    datasheet: str = LORD,
    origin: float = 10,
    seed: str = "section11",
) -> tuple[GameState, UnitInstance, UnitInstance]:
    unit = definitions.unit(datasheet)
    enemy = definitions.unit(LORD, army_id="enemy", identity="target")
    own = geometry(unit, (Pose.at(origin, 10),) * len(unit.own_models))[0]
    other = geometry(enemy, (Pose.at(20, 10),), enemy=True)[0]
    assert isinstance(own.base, CircularBase)
    assert isinstance(other.base, CircularBase)
    x = origin + own.base.radius + other.base.radius + gap
    state = native_state(
        definitions,
        unit,
        tuple(Pose.at(origin, 10 + 3 * i) for i in range(len(unit.own_models))),
        enemy=enemy,
        enemy_poses=(Pose.at(x, 10),),
    )
    state.game_id = seed
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    attach_mission(state)
    # A second independently eligible native unit keeps legal continuations at
    # Charge selection rather than entering the unrelated Fight phase.
    spare = definitions.unit(LORD, identity="spare")
    add_unit(state, spare, (Pose.at(x, 20),))
    return state, unit, enemy


def session_for(definitions: Section02Definitions, state: GameState) -> LocalGameSession:
    from warhammer40k_core.engine.core_ability_materialization import (
        record_core_deadly_demise_sources_for_unit,
        record_core_feel_no_pain_sources_for_unit,
        record_core_fights_first_sources_for_unit,
    )

    # The constructed battle boundary includes native static abilities, which
    # normal lifecycle submissions otherwise materialize on their first call.
    for army in state.army_definitions:
        for unit in army.units:
            record_core_deadly_demise_sources_for_unit(state=state, unit=unit)
            record_core_feel_no_pain_sources_for_unit(state=state, unit=unit)
            record_core_fights_first_sources_for_unit(state=state, unit=unit)
    config = movement_session(definitions, state).lifecycle.config
    handler = ChargePhaseHandler(ruleset_descriptor=config.ruleset_descriptor)
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.CHARGE: handler},
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session = LocalGameSession(
        GameLifecycle(
            state=state, _config=config, _charge_phase_handler=handler, _battle_round_flow=flow
        )
    )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return session


def case(
    definitions: Section02Definitions, **kwargs: object
) -> tuple[LocalGameSession, GameState, UnitInstance, UnitInstance]:
    # Deliberately explicit arguments belong in state_case; callers use that
    # typed entry point for custom scenes.
    assert not kwargs
    state, unit, enemy = state_case(definitions)
    return session_for(definitions, state), state, unit, enemy


def choose(
    session: LocalGameSession, option: str, *, result_id: str = "section11:select"
) -> DecisionRequest:
    request = pending(session)
    status = session.submit_option(
        request_id=request.request_id, result_id=result_id, option_id=option
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    return pending(session)


def begin(session: LocalGameSession) -> DecisionRequest:
    status = session.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    return pending(session)


def select(
    session: LocalGameSession, unit: UnitInstance, *, skies: bool = False
) -> DecisionRequest:
    request = begin(session)
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict)
        and o.payload.get("unit_instance_id") == unit.unit_instance_id
        and o.payload.get("take_to_the_skies") is skies
    )
    return choose(session, option.option_id)


def targets(session: LocalGameSession, ids: tuple[str, ...]) -> DecisionRequest:
    request = pending(session)
    assert request.decision_type == "select_charge_targets"
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict) and o.payload.get("target_ids") == sorted(ids)
    )
    return choose(session, option.option_id, result_id="section11:targets")


def roll(session: LocalGameSession) -> ChargeRollResult:
    value = events(session, "charge_roll_resolved")[-1]["roll_result"]
    return ChargeRollResult.from_payload(cast(ChargeRollResultPayload, value))


def events(session: LocalGameSession, kind: str) -> list[dict[str, JsonValue]]:
    return [
        cast(dict[str, JsonValue], e.payload)
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == kind
    ]


def witness(state: GameState, unit_id: str, dx: float, dy: float = 0) -> PathWitness:
    placed = charge_movement_placement(scenario=scenario(state), unit_instance_id=unit_id)
    return PathWitness.for_paths(
        tuple(
            (
                p.model_instance_id,
                (
                    p.pose,
                    Pose.at(p.pose.position.x + dx, p.pose.position.y + dy, p.pose.position.z),
                ),
            )
            for p in placed.model_placements
        )
    )


def propose(
    session: LocalGameSession,
    unit_id: str,
    ids: tuple[str, ...],
    path: PathWitness | None,
    *,
    result_id: str = "section11:move",
) -> LifecycleStatus:
    request = pending(session)
    proposal = ChargeMoveProposal(
        request.request_id,
        ProposalKind.CHARGE_MOVE,
        unit_id,
        "charge_move",
        MovementMode.CHARGE,
        ids,
        path,
    )
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(proposal.to_payload()),
    )


def resolution(
    state: GameState, unit_id: str, ids: tuple[str, ...], path: PathWitness, maximum: float = 6
) -> ChargeMoveResolution:
    return resolve_charge_move(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=charge_movement_placement(
            scenario=scenario(state), unit_instance_id=unit_id
        ),
        selected_target_unit_instance_ids=ids,
        maximum_distance_inches=maximum,
        path_witness=path,
    )


def move_target(state: GameState, enemy: UnitInstance, pose: Pose) -> None:
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=tuple(
                        placement(enemy, (pose,), enemy=True)
                        if p.unit_instance_id == enemy.unit_instance_id
                        else p
                        for p in a.unit_placements
                    ),
                )
                if a.player_id == "opponent"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )


def modifier(
    state: GameState,
    unit_id: str,
    delta: float,
    *,
    kind: str = "modify_dice_roll",
    identity: str = "constructed:charge-modifier",
) -> None:
    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.effects import EffectExpiration

    parameters: dict[str, JsonValue] = {"delta": delta}
    if kind == "modify_dice_roll":
        parameters = {"delta": int(delta), "roll_type": "charge"}
    effect = generic_effect(
        effect_id=identity,
        owner_player_id="owner",
        target_unit_instance_ids=(unit_id,),
        target_kind="this_unit",
        effect_kind=kind,
        parameters=parameters,
    )
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=BattlePhase.CHARGE, player_id="owner"
            ),
        )
    )
