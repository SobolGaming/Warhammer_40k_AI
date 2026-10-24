"""Native kernels and cached facade authority; no startup or prior phase traversal."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import cast

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state, placement
from tests.support.section03_session import movement_session
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.phases.shooting_model import _default_stratagem_index
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

NATIVE_IDS = ("000004080", "000004078", "000004090", "000000593", "000000592", "000004088")


@pytest.fixture(scope="session")
def section04_mission() -> Iterator[MissionSetup]:
    start = perf_counter()
    mission = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-2",
        terrain_layout_id="disruption-vs-reconnaissance-layout-2",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
    )
    mission = replace(mission, terrain_features=(), terrain_areas=(), objective_terrain_areas=())
    before = mission.to_payload()
    print(
        f"Section04 mission preparation: {perf_counter() - start:.6f}s; "
        "once, shooting Action boundary dependency"
    )
    yield mission
    assert mission.to_payload() == before


@pytest.fixture(scope="session")
def section04_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    seconds = perf_counter() - start

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    print(
        f"Section04 preparation: {seconds:.6f}s; one selected build, "
        f"{len(NATIVE_IDS)} native definitions"
    )
    yield Section02Definitions(package, seconds)
    assert digest() == before


def combat_state(
    definitions: Section02Definitions,
    unit: UnitInstance,
    *,
    phase: BattlePhase = BattlePhase.SHOOTING,
    target: UnitInstance | None = None,
    distance: float = 8,
) -> GameState:
    enemy = target or definitions.unit("000004078", identity="target", army_id="enemy")
    state = native_state(
        definitions,
        unit,
        tuple(Pose.at(10, 10 + 2 * i) for i in range(len(unit.own_models))),
        enemy=enemy,
        enemy_poses=tuple(Pose.at(10 + distance, 10 + 2 * i) for i in range(len(enemy.own_models))),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    if phase is BattlePhase.FIGHT:
        policy = state.runtime_ruleset_descriptor().fight_policy
        state.fight_phase_state = FightPhaseState.start(
            battle_round=1,
            active_player_id="owner",
            policy=policy,
            engaged_at_fight_step_start_unit_ids=(unit.unit_instance_id, enemy.unit_instance_id),
            fights_first_registry=FightsFirstRegistry(),
        ).with_current_step(current_step=FightPhaseStepKind.FIGHT, policy=policy)
    return state


def combat_session(
    definitions: Section02Definitions,
    state: GameState,
    mission: MissionSetup,
    *,
    stratagem_index: StratagemCatalogIndex | None = None,
) -> LocalGameSession:
    state.mission_setup = mission
    spare = definitions.unit("000004090", identity="spare")
    state.army_definitions[0] = replace(
        state.army_definitions[0], units=(*state.army_definitions[0].units, spare)
    )
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="owner", unit=spare)
    )
    state.army_definitions[:] = sorted(
        (
            replace(
                a,
                force_disposition_id=mission.primary_mission_assignment_for_player(
                    a.player_id
                ).force_disposition_id,
            )
            for a in state.army_definitions
        ),
        key=lambda a: a.army_id,
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            battlefield_width_inches=mission.battlefield_width_inches,
            battlefield_depth_inches=mission.battlefield_depth_inches,
            placed_armies=tuple(
                replace(
                    a, unit_placements=(*a.unit_placements, placement(spare, grid(spare, 10, 30)))
                )
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    config = movement_session(definitions, state).lifecycle.config
    shooting = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        stratagem_index=stratagem_index or _default_stratagem_index(),
    )
    fight = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.SHOOTING: shooting, BattlePhase.FIGHT: fight},
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session = LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _shooting_phase_handler=shooting,
            _fight_phase_handler=fight,
            _battle_round_flow=flow,
        )
    )
    handler = fight if state.current_battle_phase is BattlePhase.FIGHT else shooting
    handler.begin_phase(state=state, decisions=session.lifecycle.decision_controller)
    request = pending(session)
    if request.decision_type == "start_mission_action":
        choose(session, request, "continue_to_shooting")
    return session


def add_enemy(
    definitions: Section02Definitions,
    state: GameState,
    *,
    identity: str = "other",
    x: float = 18,
    y: float = 14,
) -> UnitInstance:
    enemy = definitions.unit("000004078", army_id="enemy", identity=identity)
    state.army_definitions[:] = [
        replace(a, units=(*a.units, enemy)) if a.player_id == "opponent" else a
        for a in state.army_definitions
    ]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="opponent", unit=enemy)
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=(
                        *a.unit_placements,
                        placement(enemy, (Pose.at(x, y),), enemy=True),
                    ),
                )
                if a.player_id == "opponent"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    return enemy


def pending(session: LocalGameSession) -> DecisionRequest:
    requests = session.lifecycle.decision_controller.queue.pending_requests
    assert len(requests) == 1
    return requests[0]


def choose(session: LocalGameSession, request: DecisionRequest, option: str) -> None:
    status = session.submit_option(
        request_id=request.request_id, result_id=f"{request.request_id}:section04", option_id=option
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def body(request: DecisionRequest) -> dict[str, JsonValue]:
    assert isinstance(request.payload, dict)
    return request.payload


def weapon_rows(request: DecisionRequest) -> list[dict[str, JsonValue]]:
    proposal = cast(dict[str, JsonValue], body(request)["proposal_request"])
    return cast(list[dict[str, JsonValue]], proposal["available_weapons"])


def shooting_payload(
    request: DecisionRequest, rows: list[dict[str, JsonValue]], targets: Sequence[str | None]
) -> JsonValue:
    proposal = cast(dict[str, JsonValue], body(request)["proposal_request"])
    payload = {
        key: proposal[key]
        for key in (
            "battle_round",
            "unit_instance_id",
            "source_decision_request_id",
            "source_decision_result_id",
            "visibility_cache_key",
        )
    }
    payload.update(
        player_id=request.actor_id,
        proposal_request_id=request.request_id,
        proposal_kind="shooting_declaration",
        firing_deck_selection=None,
        declarations=[
            {
                "weapon_instance_id": row["weapon_instance_id"],
                "attacker_model_instance_id": row["model_instance_id"],
                "wargear_id": row["wargear_id"],
                "weapon_profile_id": row["weapon_profile_id"],
                "target_unit_instance_id": target,
                "shooting_type": "normal",
                "selected_weapon_ability_ids": [],
                "firing_deck_source_unit_instance_id": None,
                "firing_deck_source_model_instance_id": None,
            }
            for row, target in zip(rows, targets, strict=True)
        ],
    )
    return validate_json_value(payload)


def declare_shooting(
    session: LocalGameSession,
    request: DecisionRequest,
    rows: list[dict[str, JsonValue]],
    targets: Sequence[str | None],
) -> None:
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"{request.request_id}:section04",
        payload=shooting_payload(request, rows, targets),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def shooting_request(session: LocalGameSession, unit_id: str) -> DecisionRequest:
    request = pending(session)
    assert request.decision_type == "select_shooting_unit"
    choose(session, request, unit_id)
    request = pending(session)
    assert request.decision_type == "select_shooting_type"
    choose(session, request, "normal")
    return pending(session)


def finish_attacks(session: LocalGameSession) -> None:
    for _ in range(80):
        if any(
            e.event_type == "attack_sequence_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        ):
            return
        request = pending(session)
        assert request.decision_type not in {
            "submit_shooting_declaration",
            "submit_melee_declaration",
            "submit_parameterized_payload",
        }, request
        option = next(
            (
                o.option_id
                for o in request.options
                if o.option_id in {"decline", "keep", "keep_all_modifiers"}
            ),
            request.options[0].option_id,
        )
        choose(session, request, option)
    raise AssertionError("Section04 bounded attack did not finish")
