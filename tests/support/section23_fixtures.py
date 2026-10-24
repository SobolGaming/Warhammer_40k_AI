"""Selected native Aircraft definitions; fresh explicit Core boundary scenes."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.unit_keyword_helpers import with_unit_keywords
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

LORD = "000004078"
AIRCRAFT = LORD
BODY = "000004080"
AVENGERS = "000000593"
SPAWN = "000004090"
HAWKS = "000000600"
IDS = (LORD, BODY, AVENGERS, SPAWN, HAWKS)


@pytest.fixture(scope="session")
def section23_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    seconds = perf_counter() - start
    print(f"Section23 preparation: {seconds:.6f}s; one immutable five-datasheet package")
    yield Section02Definitions(package, seconds)
    assert digest() == before


def scene(
    d: Section02Definitions,
    *,
    aircraft_attacker: bool = False,
    distance: float = 8,
) -> tuple[GameState, UnitInstance, UnitInstance]:
    own = d.unit(LORD)
    enemy = d.unit(LORD, army_id="enemy", identity="target")
    # Explicit Core AIRCRAFT input on supported native bodies. The selected
    # native catalog has no admitted Aircraft geometry/provider; do not invent one.
    if aircraft_attacker:
        own = with_unit_keywords(own, keywords=(*own.keywords, "AIRCRAFT", "FLY"))
    else:
        enemy = with_unit_keywords(enemy, keywords=(*enemy.keywords, "AIRCRAFT", "FLY"))
    state = native_state(
        d, own, (Pose.at(15, 15),), enemy=enemy, enemy_poses=(Pose.at(15 + distance, 15),)
    )
    return state, own, enemy
