"""Section18 native selections and fresh transport-boundary kernels.

Capacity profiles, cargo and optional permission/history premises are explicitly
constructed Core inputs. Native definitions do not certify roster, provider or
starting-cargo admission. No unrelated setup/mission/phase traversal is used.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from math import cos, radians, sin
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, placement, scenario
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission, movement_mission, unplace
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    DisembarkSelection,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
    TransportRestrictionOverride,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

INFRACTORS = "000004080"
LORD = "000004078"
WAVE = "000000599"
YRIEL = "000004193"
AVENGERS = "000000593"
RANGERS = "000000592"
IDS = (INFRACTORS, LORD, WAVE, YRIEL, AVENGERS, RANGERS, "000004090")


@pytest.fixture(scope="session")
def section18_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    mission = movement_mission()
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    mission_before = mission.to_payload()
    seconds = perf_counter() - start
    print(f"Section18 preparation: {seconds:.6f}s; seven native definitions, shared mission")
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )
    assert mission.to_payload() == mission_before


@dataclass
class TransportScene:
    state: GameState
    passenger: UnitInstance
    transport: UnitInstance
    session: LocalGameSession

    @property
    def scenario(self) -> BattlefieldScenario:
        return scenario(self.state)

    @property
    def carrier_placement(self) -> UnitPlacement:
        assert self.state.battlefield_state is not None
        return self.state.battlefield_state.unit_placement_by_id(self.transport.unit_instance_id)

    @property
    def cargo(self) -> TransportCargoState:
        value = self.state.transport_cargo_state_for_transport(self.transport.unit_instance_id)
        assert value is not None
        return value

    def selection(
        self,
        mode: DisembarkModeKind = DisembarkModeKind.TACTICAL_DISEMBARK,
        status: TransportMovementStatus = TransportMovementStatus.NOT_MOVED,
        *,
        poses: tuple[Pose, ...] | None = None,
        overrides: tuple[TransportRestrictionOverride, ...] = (),
    ) -> DisembarkSelection:
        # Ordinary single-model native Yriel. Multimodel/attached tests supply
        # their complete physical placements explicitly.
        attempted = placement(self.passenger, poses or (Pose.at(23, 20),))
        return DisembarkSelection(
            "owner",
            self.state.battle_round,
            self.passenger.unit_instance_id,
            self.transport.unit_instance_id,
            attempted,
            mode,
            status,
            overrides,
        )


def transport_scene(
    d: Section02Definitions,
    *,
    embarked: bool = True,
    passenger_sheet: str = YRIEL,
    capacity: int = 12,
    passenger_poses: tuple[Pose, ...] | None = None,
    enemy_poses: tuple[Pose, ...] = (Pose.at(50, 35),),
) -> TransportScene:
    carrier = d.unit(WAVE, identity="carrier")
    passenger = d.unit(passenger_sheet, identity="passenger")
    enemy = d.unit(LORD, identity="enemy", army_id="enemy")
    state = native_state(d, carrier, (Pose.at(20, 20),), enemy=enemy, enemy_poses=enemy_poses)
    poses = passenger_poses or tuple(
        Pose.at(23, 19 + i * 1.5) for i in range(len(passenger.own_models))
    )
    add_unit(state, passenger, poses)
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(8, 32),))
    attach_mission(state)
    if embarked:
        state.replace_battlefield_state(unplace(state, passenger))
    cargo = TransportCargoState(
        "owner",
        carrier.unit_instance_id,
        TransportCapacityProfile(
            WAVE, capacity, ("INFANTRY",), source_id="constructed:s18:capacity"
        ),
        (passenger.unit_instance_id,) if embarked else (),
    )
    state.record_transport_cargo_state(cargo)
    return TransportScene(state, passenger, carrier, movement_session(d, state))


def replace_passenger(scene: TransportScene, unit: UnitInstance) -> None:
    assert unit.unit_instance_id == scene.passenger.unit_instance_id
    scene.state.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                unit if u.unit_instance_id == unit.unit_instance_id else u for u in a.units
            ),
        )
        for a in scene.state.army_definitions
    ]
    scene.passenger = unit


def contact_poses(scene: TransportScene, *, extra: float = 0.02) -> tuple[Pose, ...]:
    rt = scene.transport.own_models[0].geometry.parts[0].radius_x_inches
    return tuple(
        Pose.at(
            20 + (rt + m.geometry.parts[0].radius_x_inches + extra) * cos(radians(70 * i)),
            20 + (rt + m.geometry.parts[0].radius_x_inches + extra) * sin(radians(70 * i)),
        )
        for i, m in enumerate(scene.passenger.own_models)
    )


def elevate_carrier(scene: TransportScene) -> None:
    """Declared 5.6-inch platform; native carrier fills its small supported top.

    A constructed terrain input, never an official Companion layout or model grant.
    It has ordinary ground next to the platform and no tactical landing surface.
    """
    from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
    from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
    from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition

    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=20,
        center_y_inches=20,
        width_inches=10,
        depth_inches=10,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        feature_id="constructed:s18:carrier-platform",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=20,
        footprint_center_y_inches=20,
        footprint_width_inches=10,
        footprint_depth_inches=10,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="top",
                center_x_inches=20,
                center_y_inches=20,
                bottom_z_inches=5.6,
                width_inches=2.4,
                depth_inches=2.4,
                thickness_inches=0.12,
            ),
        ),
    )
    assert scene.state.mission_setup is not None
    scene.state.mission_setup = replace(
        scene.state.mission_setup,
        battlefield_layout_id=None,
        deployment_map_id="constructed:s18:platform-zones",
        terrain_layout_id="constructed:s18:platform-layout",
        terrain_features=(feature,),
        terrain_areas=(),
        objective_terrain_areas=(),
        battlefield_regions=(),
    )
    assert scene.state.battlefield_state is not None
    carrier = scene.carrier_placement
    scene.state.replace_battlefield_state(
        replace(
            scene.state.battlefield_state.with_unit_placement(
                replace(
                    carrier,
                    model_placements=tuple(
                        replace(p, pose=Pose.at(20, 20, 5.6)) for p in carrier.model_placements
                    ),
                )
            ),
            terrain_features=(feature,),
        )
    )
