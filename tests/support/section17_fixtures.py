"""Section17 native definitions and explicit minimal physical checkpoints.

Native army definitions are immutable/shared; each case owns fresh units/state.
No roster, preceding phase, mission play or native FRAME provider is inferred.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from functools import cache
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section03_session import movement_session
from tests.support.section04_fixtures import add_enemy, combat_state
from tests.support.section09_fixtures import add_unit, attach_mission
from tests.support.section10_fixtures import shooting_session
from tests.unit_keyword_helpers import with_unit_keywords
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

LORD = "000004078"
SPAWN = "000004090"
PRINCE = "000004086"
DEFILER = "000000969"
IDS = (LORD, SPAWN, PRINCE, DEFILER, "000004080")


@cache
def native_mission() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-2",
        terrain_layout_id="disruption-vs-reconnaissance-layout-2",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
    )


@cache
def open_mission() -> MissionSetup:
    # Physical proposal metadata only: explicitly empty custom geometry kernel.
    return replace(
        native_mission(),
        battlefield_layout_id=None,
        terrain_features=(),
        terrain_areas=(),
        objective_terrain_areas=(),
    )


@pytest.fixture(scope="session")
def section17_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    missions = (native_mission(), open_mission())
    original_missions = tuple(m.to_payload() for m in missions)
    seconds = perf_counter() - start
    print(
        f"Section17 preparation: {seconds:.6f}s; five native definitions, shared mission resources"
    )
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )
    assert tuple(m.to_payload() for m in missions) == original_missions


def movement_scene(
    d: Section02Definitions, sheet: str, *, friendly: bool = False, blocker_sheet: str = LORD
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    unit = d.unit(sheet)
    # Defiler has a larger native footprint; both endpoints remain unengaged.
    middle = 16 if sheet == DEFILER else 14
    blocker = d.unit(
        blocker_sheet, identity="blocker", army_id="section02" if friendly else "enemy"
    )
    state = (
        native_state(
            d,
            unit,
            (Pose.at(10, 10),),
            enemy=d.unit(LORD, identity="far", army_id="enemy"),
            enemy_poses=(Pose.at(40, 35),),
        )
        if friendly
        else native_state(
            d,
            unit,
            (Pose.at(10, 10),),
            enemy=blocker,
            enemy_poses=tuple(Pose.at(middle, 10 + 2 * i) for i in range(len(blocker.own_models))),
        )
    )
    if friendly:
        add_unit(
            state,
            blocker,
            tuple(Pose.at(middle, 10 + 2 * i) for i in range(len(blocker.own_models))),
        )
    attach_mission(state)
    add_unit(state, d.unit(SPAWN, identity="spare"), (Pose.at(8, 32), Pose.at(10, 32)))
    return movement_session(d, state), state, unit


def shooting_scene(
    d: Section02Definitions,
    *,
    attacker_sheet: str = LORD,
    target_sheet: str = DEFILER,
    mutual: bool = False,
    third_party: bool = True,
) -> tuple[LocalGameSession, GameState, UnitInstance, UnitInstance]:
    attacker = d.unit(attacker_sheet)
    target = d.unit(target_sheet, identity="target", army_id="enemy")
    distance = (
        7
        if mutual and attacker_sheet == target_sheet == DEFILER
        else 5
        if mutual and DEFILER in (attacker_sheet, target_sheet)
        else 2.5
        if mutual
        else 12
    )
    state = combat_state(d, attacker, target=target, distance=distance)
    if third_party:
        # Friendly companion engages the target while the firing unit stays clear.
        add_unit(
            state,
            d.unit(LORD, identity="companion"),
            (Pose.at(10 + distance, 14.5 if target_sheet == DEFILER else 12.5),),
        )
    return shooting_session(d, state, open_mission()), state, attacker, target


def frame_unit(d: Section02Definitions, *, framed: bool = True) -> UnitInstance:
    """Native Lord plus an explicit two-prism body and optional FRAME premise.

    The body supplement is an exact constructed shape, not native model dimensions
    or a datasheet grant. Both controls retain identical physical parts.
    """
    unit = d.unit(LORD)
    if framed:
        unit = with_unit_keywords(unit, keywords=(*unit.keywords, "FRAME"))
    model = unit.own_models[0]
    body = ModelBodyPart("overhang", CircularBase(0.5), 3, 0, 1, 1, "constructed:s17:body")
    return replace(
        unit, own_models=(replace(model, geometry=replace(model.geometry, body_parts=(body,))),)
    )


def vehicle_diagram_scene(
    d: Section02Definitions,
) -> tuple[LocalGameSession, GameState, UnitInstance]:
    vehicle = d.unit(DEFILER)
    state = combat_state(d, vehicle, distance=5)
    add_enemy(d, state, identity="a", x=10, y=22)
    return shooting_session(d, state, open_mission()), state, vehicle
