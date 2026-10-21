"""Engaged native Fight checkpoints. No muster, Charge, mission play or replay prehistory."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import cast

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry, native_state, placement
from tests.support.section03_session import movement_session
from tests.support.section04_fixtures import body, choose, pending, weapon_rows
from tests.support.section09_fixtures import attach_mission
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    FightPhaseStepKind,
    MovementMode,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.core_ability_materialization import (
    record_core_deadly_demise_sources_for_unit,
    record_core_feel_no_pain_sources_for_unit,
    record_core_fights_first_sources_for_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.fight_resolution import FightMovementProposal
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

LORD = "000004078"
SPAWN = "000004090"
SERPENT = "000000599"
IDS = (LORD, SPAWN, SERPENT, "000004080")


@pytest.fixture(scope="session")
def section12_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    seconds = perf_counter() - start
    print(
        f"Section12 immutable native definition preparation: {seconds:.6f}s; {len(IDS)} definitions"
    )
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


def engaged_case(
    definitions: Section02Definitions,
    *,
    gap: float = 1.5,
    datasheet: str = LORD,
    seed: str = "section12",
) -> tuple[GameState, UnitInstance, UnitInstance]:
    unit = definitions.unit(datasheet)
    enemy = definitions.unit(LORD, army_id="enemy", identity="target")
    own = geometry(unit, tuple(Pose.at(10, 10 + 2.5 * i) for i in range(len(unit.own_models))))[0]
    other = geometry(enemy, (Pose.at(20, 10),), enemy=True)[0]
    assert isinstance(own.base, CircularBase)
    assert isinstance(other.base, CircularBase)
    x = 10 + own.base.radius + other.base.radius + gap
    state = native_state(
        definitions,
        unit,
        tuple(Pose.at(10, 10 + 2.5 * i) for i in range(len(unit.own_models))),
        enemy=enemy,
        enemy_poses=(Pose.at(x, 10),),
    )
    state.game_id = seed
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    attach_mission(state)
    from warhammer40k_core.engine.fight_order import unit_is_currently_engaged

    assert unit_is_currently_engaged(state=state, unit_instance_id=unit.unit_instance_id)
    return state, unit, enemy


def set_pose(
    state: GameState, unit: UnitInstance, poses: tuple[Pose, ...], *, enemy: bool = False
) -> None:
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=tuple(
                        placement(unit, poses, enemy=enemy)
                        if p.unit_instance_id == unit.unit_instance_id
                        else p
                        for p in a.unit_placements
                    ),
                )
                for a in state.battlefield_state.placed_armies
            ),
        )
    )


def add_native(
    state: GameState, unit: UnitInstance, poses: tuple[Pose, ...], *, enemy: bool = False
) -> None:
    player = "opponent" if enemy else "owner"
    state.army_definitions[:] = [
        replace(a, units=(*a.units, unit)) if a.player_id == player else a
        for a in state.army_definitions
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id=player, unit=unit)
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a, unit_placements=(*a.unit_placements, placement(unit, poses, enemy=enemy))
                )
                if a.player_id == player
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )


def checkpoint(
    state: GameState, step: FightPhaseStepKind, *, engaged_ids: tuple[str, ...] | None = None
) -> None:
    """Explicit phase checkpoint; does not fabricate prior decision/event history."""
    assert state.active_player_id is not None
    policy = state.runtime_ruleset_descriptor().fight_policy
    ids = (
        engaged_ids
        if engaged_ids is not None
        else tuple(u.unit_instance_id for a in state.army_definitions for u in a.units)
    )
    state.fight_phase_state = FightPhaseState.start(
        battle_round=1,
        active_player_id=state.active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=ids,
        fights_first_registry=FightsFirstRegistry.from_state(state),
    ).with_current_step(current_step=step, policy=policy)


def session_for(
    definitions: Section02Definitions,
    state: GameState,
    *,
    decisions: DecisionController | None = None,
) -> LocalGameSession:
    for a in state.army_definitions:
        for u in a.units:
            record_core_deadly_demise_sources_for_unit(state=state, unit=u)
            record_core_feel_no_pain_sources_for_unit(state=state, unit=u)
            record_core_fights_first_sources_for_unit(state=state, unit=u)
    config = movement_session(definitions, state).lifecycle.config
    fight = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: fight},
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session = LocalGameSession(
        GameLifecycle(
            decision_controller=decisions if decisions is not None else DecisionController(),
            state=state,
            _config=config,
            _fight_phase_handler=fight,
            _battle_round_flow=flow,
        )
    )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    return session


def begin(session: LocalGameSession) -> DecisionRequest:
    for _ in range(12):
        status = session.advance_until_decision_or_terminal()
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
        request = pending(session)
        if request.decision_type == "resolve_sequencing_order":
            option = request.options[0]
        elif request.decision_type == "select_faction_rule_fight_phase_start_option":
            option = next(o for o in request.options if o.option_id.endswith(":decline"))
        else:
            return request
        choose(session, request, option.option_id)
    raise AssertionError("bounded native start ability decline exhausted")


def events(session: LocalGameSession, kind: str) -> list[dict[str, JsonValue]]:
    return [
        cast(dict[str, JsonValue], e.payload)
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == kind
    ]


def paths(state: GameState, unit_ids: tuple[str, ...], dx: float, dy: float = 0) -> PathWitness:
    assert state.battlefield_state is not None
    return PathWitness.for_paths(
        tuple(
            (
                p.model_instance_id,
                (
                    p.pose,
                    Pose.at(p.pose.position.x + dx, p.pose.position.y + dy, p.pose.position.z),
                ),
            )
            for a in state.battlefield_state.placed_armies
            for u in a.unit_placements
            if u.unit_instance_id in unit_ids
            for p in u.model_placements
        )
    )


def move_payload(
    request: DecisionRequest,
    *,
    targets: tuple[str, ...] = (),
    witness: PathWitness | None = None,
    mode: ConsolidationModeKind | None = None,
    objective: str | None = None,
) -> JsonValue:
    r = MovementProposalRequest.from_decision_request_payload(request.payload)
    k = r.proposal_kind
    assert r.movement_phase_action is not None
    p = FightMovementProposal(
        r.request_id,
        k,
        r.unit_instance_id,
        r.movement_phase_action,
        MovementMode.PILE_IN if k is ProposalKind.PILE_IN else MovementMode.CONSOLIDATE,
        pile_in_target_unit_instance_ids=targets if k is ProposalKind.PILE_IN else (),
        consolidation_mode=mode,
        consolidate_target_unit_instance_ids=targets if k is ProposalKind.CONSOLIDATE else (),
        objective_id=objective,
        witness=witness,
    )
    return validate_json_value(p.to_payload())


def submit_move(
    session: LocalGameSession,
    *,
    targets: tuple[str, ...] = (),
    witness: PathWitness | None = None,
    mode: ConsolidationModeKind | None = None,
    objective: str | None = None,
    identity: str = "move",
) -> LifecycleStatus:
    request = pending(session)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"{request.request_id}:{identity}",
        payload=move_payload(
            request, targets=targets, witness=witness, mode=mode, objective=objective
        ),
    )


def decline_moves(session: LocalGameSession, *, limit: int = 12) -> DecisionRequest:
    for _ in range(limit):
        request = begin(session)
        if request.decision_type != "submit_movement_proposal":
            return request
        result = submit_move(session)
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    raise AssertionError("bounded Fight move drain exhausted")


def select_fight(
    session: LocalGameSession, unit_id: str, fight_type: str = "normal"
) -> DecisionRequest:
    r = begin(session)
    assert r.decision_type == "select_fight_activation", r
    option = next(
        o
        for o in r.options
        if isinstance(o.payload, dict)
        and o.payload.get("unit_instance_id") == unit_id
        and o.payload.get("fight_type") == fight_type
    )
    choose(session, r, option.option_id)
    return pending(session)


def melee_payload(request: DecisionRequest, *, attack: bool = True) -> JsonValue:
    p = cast(dict[str, JsonValue], body(request)["proposal_request"])
    payload = {
        k: p[k]
        for k in (
            "battle_round",
            "unit_instance_id",
            "source_decision_request_id",
            "source_decision_result_id",
        )
    }
    payload.update(
        player_id=request.actor_id,
        proposal_kind="melee_declaration",
        proposal_request_id=request.request_id,
        declarations=[],
    )
    if attack:
        row = next(row for row in weapon_rows(request) if row["engaged_target_unit_instance_ids"])
        targets = cast(list[str], row["engaged_target_unit_instance_ids"])
        assert targets
        payload["declarations"] = [
            {
                "attacker_model_instance_id": row["model_instance_id"],
                "wargear_id": row["wargear_id"],
                "weapon_profile_id": row["weapon_profile_id"],
                "weapon_instance_id": row["weapon_instance_id"],
                "selected_weapon_ability_ids": [],
                "target_allocations": [{"target_unit_instance_id": targets[0]}],
            }
        ]
    return validate_json_value(payload)


def declare(session: LocalGameSession, *, attack: bool = True) -> LifecycleStatus:
    r = pending(session)
    assert r.decision_type == "submit_melee_declaration", r
    return session.submit_parameterized_payload(
        request_id=r.request_id,
        result_id=f"{r.request_id}:declare",
        payload=melee_payload(r, attack=attack),
    )


def finite_default(session: LocalGameSession) -> None:
    r = pending(session)
    assert r.options
    assert r.decision_type not in {
        "submit_movement_proposal",
        "submit_melee_declaration",
    }, r
    option = next(
        (o for o in r.options if o.option_id in {"decline", "keep", "keep_all_modifiers"}),
        r.options[0],
    )
    choose(session, r, option.option_id)


def finish_activation(session: LocalGameSession) -> DecisionRequest:
    for _ in range(100):
        request = begin(session)
        if request.decision_type in {"select_fight_activation", "submit_movement_proposal"}:
            return request
        finite_default(session)
    raise AssertionError("bounded native activation did not complete")
