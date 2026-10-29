"""Objective cases use selected native definitions and fresh mutable graphs.

No roster admission or previous phase is asserted. Elevated cases are explicit
already-supported measurement checkpoints. Source permission for securing is
either native catalog production or explicitly labelled constructed input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

IDS = ("000004080", "000004078", "000004079", "000004090", "000000593", "000000968")


@pytest.fixture(scope="session")
def section14_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    seconds = perf_counter() - start

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    print(f"Section14 preparation: {seconds:.6f}s; one selected build, {len(IDS)} definitions")
    yield Section02Definitions(package, seconds)
    assert digest() == before


def objective_state(
    definitions: Section02Definitions,
    *,
    subject_sheet: str = "000004078",
    x: float = 10,
    z: float = 0,
    enemy_x: float = 30,
) -> tuple[GameState, UnitInstance, UnitInstance]:
    unit = definitions.unit(subject_sheet)
    enemy = definitions.unit("000004078", identity="enemy", army_id="enemy")
    state = native_state(
        definitions,
        unit,
        tuple(Pose.at(x, 10 + 1.5 * i, z) for i in range(len(unit.own_models))),
        enemy=enemy,
        enemy_poses=(Pose.at(enemy_x, 10),),
    )
    return state, unit, enemy


def context(state: GameState, *markers: ObjectiveMarker) -> ObjectiveControlContext:
    return ObjectiveControlContext(
        game_id=state.game_id,
        scenario=scenario(state),
        objective_markers=markers or (ObjectiveMarker("s14:objective", "Objective", 10, 10),),
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.MOVEMENT.value,
        battle_round=state.battle_round,
        active_player_id="owner",
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        state=None,
    )
