"""Terrain kernels: immutable selected definitions, fresh physical graphs.

Keyword matrices and tiny window probes are explicit constructed checkpoints.
Native Movement/Shooting scenes use unchanged datasheets and public decisions.
The reused mission object supplies mandatory proposal geometry only; no mission
play, mustering, preceding phase traversal or roster admission is exercised.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import (
    AVENGERS,
    CHAOS_SPAWN,
    INFRACTORS,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from tests.support.section03_fixtures import geometry, native_state, scenario
from tests.support.section04_fixtures import combat_session
from tests.support.section09_fixtures import attach_mission
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    SymmetryAxis,
    TerrainAreaLocalTransform,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.game_state import GameState, RangedAttackHistoryRecord
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting_eligibility import _hidden_target_model_ids
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityResult
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainVolume,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model, ModelVolume

IDS = (INFRACTORS, LORD_EXULTANT, CHAOS_SPAWN, AVENGERS, MAULERFIEND, "000000599", "000000969")


@pytest.fixture(scope="session")
def section13_definitions(
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
    print(f"Section13 preparation: {seconds:.6f}s; one indexed build, {len(IDS)} definitions")
    yield Section02Definitions(package, seconds)
    assert digest() == before


def feature(
    classification: TerrainAreaClassification = TerrainAreaClassification.DENSE,
    *,
    x: float = 14,
    y: float = 10,
    height: float = 4,
    width: float = 1,
    depth: float = 8,
    floor: bool = False,
    identity: str = "s13:feature",
) -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=x,
        center_y_inches=y,
        width_inches=width,
        depth_inches=depth,
        display_template_id=identity,
    )
    return TerrainFeatureDefinition(
        feature_id=identity,
        feature_kind=TerrainFeatureKind.RUINS
        if floor
        else TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        classification=classification,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=width,
        footprint_depth_inches=depth,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                "support-wall", x, y + depth / 2 - 0.0625, 0, width, 0.125, height
            ),
        )
        if floor
        else (TerrainWallDefinition("wall", x, y, 0, width, depth, height),),
        floors=(TerrainFloorDefinition("floor", x, y, height, width, depth, 0.125),)
        if floor
        else (),
        source_id="constructed:section13:agreed-physical-terrain",
    )


def area(
    *,
    classification: TerrainAreaClassification = TerrainAreaClassification.LIGHT,
    x: float = 20,
    y: float = 10,
    width: float = 8,
    depth: float = 8,
    identity: str = "s13:area",
    logical: str | None = None,
) -> PlacedTerrainArea:
    polygon = tuple(
        TerrainDisplayPoint(px, py)
        for px, py in (
            (x - width / 2, y - depth / 2),
            (x + width / 2, y - depth / 2),
            (x + width / 2, y + depth / 2),
            (x - width / 2, y + depth / 2),
        )
    )
    return PlacedTerrainArea(
        identity,
        logical or identity,
        "s13:agreed-boundary",
        "ruins",
        classification,
        x,
        y,
        0,
        TerrainAreaLocalTransform.IDENTITY,
        polygon,
        "constructed:s13:layout",
        "constructed:s13:agreed-area",
        "identity",
        SymmetryAxis.NONE,
    )


def tiny(identity: str = "constructed:tiny", x: float = 10, y: float = 10, z: float = 0) -> Model:
    """Explicit simple geometric witness, not a native datasheet model."""
    return Model(identity, Pose.at(x, y, z), CircularBase(0.25), ModelVolume(0.5))


def transit(
    mover: Model,
    poses: tuple[Pose, ...],
    *,
    keywords: tuple[str, ...],
    features: tuple[TerrainFeatureDefinition, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
) -> TerrainPathLegalityResult:
    legality = MovementLegalityContext.from_keywords(
        keywords=keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    return legality.to_terrain_path_legality_context(
        moving_model=mover,
        witness=PathWitness.for_paths(((mover.model_id, poses),)),
        terrain=terrain,
        terrain_features=features,
        contact_footprint_available=True,
        sample_interval_inches=0.25,
    ).validate()


def visibility(
    observer: Model,
    targets: tuple[Model, ...],
    *,
    keywords: tuple[str, ...] = ("INFANTRY",),
    features: tuple[TerrainFeatureDefinition, ...] = (),
    areas: tuple[PlacedTerrainArea, ...] = (),
) -> TerrainVisibilityContext:
    return TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s13:physical-scene",
        observer_model=observer,
        target_models=targets,
        target_model_keywords=tuple((m.model_id, keywords) for m in targets),
        terrain_features=features,
        terrain_areas=terrain_visibility_areas_from_placements(areas),
    )


def scene(
    d: Section02Definitions,
    *,
    target_sheet: str = LORD_EXULTANT,
    target_x: float = 24,
    target_y: float = 10,
    areas: tuple[PlacedTerrainArea, ...] = (),
    features: tuple[TerrainFeatureDefinition, ...] = (),
) -> tuple[GameState, UnitInstance, UnitInstance]:
    attacker = d.unit(AVENGERS)
    target = d.unit(target_sheet, identity="target", army_id="enemy")
    state = native_state(
        d,
        attacker,
        tuple(Pose.at(10, 10 + 1.5 * i) for i in range(len(attacker.own_models))),
        enemy=target,
        enemy_poses=tuple(
            Pose.at(target_x, target_y + 2.5 * i) for i in range(len(target.own_models))
        ),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attach_mission(state)
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        terrain_areas=areas,
        terrain_features=features,
        battlefield_layout_id="constructed:s13:agreed-layout",
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=features))
    return state, attacker, target


def recent(state: GameState, target: UnitInstance, when: str) -> None:
    """Constructed exact history checkpoint, independent of weapon/dice prehistory."""
    if when == "first":
        return
    state.battle_round = 2
    if when == "none":
        return
    state.record_ranged_attack_history(
        RangedAttackHistoryRecord(
            player_id="opponent",
            unit_instance_id=target.unit_instance_id,
            battle_round=2 if when == "current" else 1,
            active_player_id="owner" if when in {"current", "old"} else "opponent",
            phase=BattlePhase.SHOOTING,
            request_id="constructed:s13:prior-shooting",
            result_id="constructed:s13:prior-shooting-result",
        )
    )


def candidate(
    d: Section02Definitions, state: GameState, attacker: UnitInstance, target: UnitInstance
) -> ShootingTargetCandidate:
    assert state.mission_setup is not None
    hidden = _hidden_target_model_ids(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        target_unit_ids=(target.unit_instance_id,),
    )
    return shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_model_ids()[0],
        weapon_profile=d.weapon(f"{AVENGERS}:avenger-shuriken-catapult"),
        target_unit_id=target.unit_instance_id,
        terrain_features=state.mission_setup.terrain_features,
        terrain_areas=state.mission_setup.terrain_areas,
        hidden_target_model_ids=hidden,
        target_unit_ids_with_recent_ranged_attacks=(target.unit_instance_id,)
        if state.unit_made_ranged_attacks_current_or_previous_turn(
            unit_instance_id=target.unit_instance_id
        )
        else (),
    )


def shooting_session(d: Section02Definitions, state: GameState) -> LocalGameSession:
    assert state.mission_setup is not None
    state.army_definitions.sort(key=lambda a: a.player_id != "owner")
    return combat_session(d, state, state.mission_setup)


def native_models(unit: UnitInstance, poses: tuple[Pose, ...]) -> tuple[Model, ...]:
    return geometry(unit, poses, enemy=unit.unit_instance_id.startswith("enemy:"))


def window(
    *, classification: TerrainAreaClassification = TerrainAreaClassification.DENSE
) -> TerrainFeatureDefinition:
    """A broad enclosed opening spanning z1..4, hence cut by the Solid z3 plane."""
    f = feature(classification, x=14, y=10, width=0.25, depth=8, height=5)
    return replace(
        f,
        walls=(
            TerrainWallDefinition("left", 14, 6.5, 0, 0.25, 1, 5),
            TerrainWallDefinition("right", 14, 13.5, 0, 0.25, 1, 5),
            TerrainWallDefinition("sill", 14, 10, 0, 0.25, 6, 1),
            TerrainWallDefinition("lintel", 14, 10, 4, 0.25, 6, 1),
        ),
    )
