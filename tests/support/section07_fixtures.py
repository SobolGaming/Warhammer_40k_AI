"""Native minimal boundary states; immutable definitions shared, mutable graphs fresh."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section03_session import movement_session
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

__all__ = ("section07_definitions", "section07_mission")
NATIVE_IDS = ("000004080", "000004078", "000000592")


@pytest.fixture(scope="session")
def section07_mission() -> Iterator[MissionSetup]:
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
    before = mission.to_payload()
    print(f"Section07 mission preparation: {perf_counter() - start:.6f}s; source geometry retained")
    yield mission
    assert mission.to_payload() == before


@pytest.fixture(scope="session")
def section07_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    seconds = perf_counter() - start
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    print(f"Section07 preparation: {seconds:.6f}s; one selected build, three native definitions")
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


def boundary_state(
    definitions: Section02Definitions,
    *,
    phase: BattlePhase = BattlePhase.COMMAND,
    active: str = "owner",
    first: str = "owner",
    battle_round: int = 1,
    mission: MissionSetup | None = None,
    datasheet_id: str = "000004078",
) -> GameState:
    state = native_state(
        definitions,
        definitions.unit(datasheet_id),
        enemy=definitions.unit("000004078", army_id="enemy", identity="target"),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.active_player_id = active
    state.turn_order = (first, "opponent" if first == "owner" else "owner")
    state.battle_round = battle_round
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    if mission is not None:
        state.mission_setup = mission
        state.army_definitions[:] = sorted(
            (
                replace(
                    army,
                    force_disposition_id=mission.primary_mission_assignment_for_player(
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
                battlefield_width_inches=mission.battlefield_width_inches,
                battlefield_depth_inches=mission.battlefield_depth_inches,
                terrain_features=mission.terrain_features,
            )
        )
    return state


def boundary_session(definitions: Section02Definitions, state: GameState) -> LocalGameSession:
    config = movement_session(definitions, state).lifecycle.config
    command = CommandPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    movement = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    shooting = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    charge = ChargePhaseHandler(ruleset_descriptor=config.ruleset_descriptor)
    fight = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
    )
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.COMMAND: command,
            BattlePhase.MOVEMENT: movement,
            BattlePhase.SHOOTING: shooting,
            BattlePhase.CHARGE: charge,
            BattlePhase.FIGHT: fight,
        },
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    return LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _command_phase_handler=command,
            _movement_phase_handler=movement,
            _shooting_phase_handler=shooting,
            _charge_phase_handler=charge,
            _fight_phase_handler=fight,
            _battle_round_flow=flow,
        )
    )


def payloads(session: LocalGameSession, event_type: str) -> list[dict[str, JsonValue]]:
    result: list[dict[str, JsonValue]] = []
    for event in session.lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            result.append(event.payload)
    return result
