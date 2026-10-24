"""Indexed native definitions with fresh case graphs; no game startup or missions."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import (
    AVENGERS,
    CHAOS_SPAWN,
    INFRACTORS,
    LORD_EXULTANT,
    MAULERFIEND,
    RANGERS,
    Section02Definitions,
)
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model

WAVE_SERPENT = "000000599"
YRIEL = "000004193"
NATIVE_IDS = (
    INFRACTORS,
    AVENGERS,
    CHAOS_SPAWN,
    MAULERFIEND,
    RANGERS,
    WAVE_SERPENT,
    YRIEL,
    LORD_EXULTANT,
)


@pytest.fixture(scope="session")
def section03_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    elapsed = perf_counter() - start

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    print(
        f"Section03 preparation: {elapsed:.6f}s; "
        f"one indexed build, {len(NATIVE_IDS)} native definitions"
    )
    yield Section02Definitions(package, elapsed)
    assert digest() == before


def placement(unit: UnitInstance, poses: tuple[Pose, ...], *, enemy: bool = False) -> UnitPlacement:
    assert len(poses) == len(unit.own_models)
    return UnitPlacement(
        "enemy" if enemy else "section02",
        "opponent" if enemy else "owner",
        unit.unit_instance_id,
        tuple(
            ModelPlacement(
                "enemy" if enemy else "section02",
                "opponent" if enemy else "owner",
                unit.unit_instance_id,
                model.model_instance_id,
                pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def grid(unit: UnitInstance, x: float = 10, y: float = 10) -> tuple[Pose, ...]:
    return tuple(Pose.at(x + 2 * (i % 3), y + 2 * (i // 3)) for i in range(len(unit.own_models)))


def native_state(
    definitions: Section02Definitions,
    unit: UnitInstance,
    poses: tuple[Pose, ...] | None = None,
    *,
    enemy: UnitInstance | None = None,
    enemy_poses: tuple[Pose, ...] | None = None,
) -> GameState:
    state = minimal_state(definitions, unit)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    placed = [
        PlacedArmy("section02", "owner", (placement(unit, grid(unit) if poses is None else poses),))
    ]
    if enemy is not None:
        army = replace(
            state.army_definitions[0], army_id="enemy", player_id="opponent", units=(enemy,)
        )
        state.army_definitions.append(army)
        state.starting_strength_records.append(
            StartingStrengthRecord.from_unit(player_id="opponent", unit=enemy)
        )
        placed.append(
            PlacedArmy(
                "enemy",
                "opponent",
                (
                    placement(
                        enemy,
                        grid(enemy, 30, 10) if enemy_poses is None else enemy_poses,
                        enemy=True,
                    ),
                ),
            )
        )
    state.record_battlefield_state(
        BattlefieldRuntimeState("section03", 60, 44, placed_armies=tuple(placed))
    )
    return state


def scenario(state: GameState) -> BattlefieldScenario:
    assert state.battlefield_state is not None
    return BattlefieldScenario(tuple(state.army_definitions), state.battlefield_state)


def geometry(
    unit: UnitInstance, poses: tuple[Pose, ...], *, enemy: bool = False
) -> tuple[Model, ...]:
    return tuple(
        geometry_model_for_placement(model=m, placement=p)
        for m, p in zip(
            unit.own_models, placement(unit, poses, enemy=enemy).model_placements, strict=True
        )
    )


def paths(unit: UnitInstance, starts: tuple[Pose, ...], ends: tuple[Pose, ...]) -> PathWitness:
    return PathWitness.for_paths(
        tuple(
            (m.model_instance_id, (s, e))
            for m, s, e in zip(unit.own_models, starts, ends, strict=True)
        )
    )


def axis_endpoint_within_range(
    origin: float, first_radius: float, second_radius: float, inches: float
) -> float:
    """Largest binary endpoint within the exact positive-axis native boundary.

    A translated native radius sum often has no exactly representable endpoint.
    Round inward explicitly for an inclusive positive fixture; keep exterior
    probes independently constructed and classified from their actual inputs.
    """
    exact = Fraction(origin) + Fraction(first_radius) + Fraction(second_radius) + Fraction(inches)
    endpoint = float(exact)
    if Fraction(endpoint) > exact:
        endpoint = math.nextafter(endpoint, -math.inf)
    assert Fraction(endpoint) <= exact < Fraction(math.nextafter(endpoint, math.inf))
    return endpoint
