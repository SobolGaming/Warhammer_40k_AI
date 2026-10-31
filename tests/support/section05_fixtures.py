"""Small fresh native-state builders and explicitly labelled Core boundary values."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

NATIVE_IDS = ("000004080", "000004078", "000000968", "000000599", "000000593")


@pytest.fixture(scope="session")
def section05_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    start = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=NATIVE_IDS, source_index_dir=selected_army_source_index
    )
    seconds = perf_counter() - start
    before = hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
    print(f"Section05 preparation: {seconds:.6f}s; one selected build, five native definitions")
    yield Section02Definitions(package, seconds)
    assert (
        hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()
        == before
    )


def contract_characteristic(
    model: ModelInstance, kind: Characteristic, value: int
) -> ModelInstance:
    updated = replace(
        model,
        characteristics=(
            *(v for v in model.characteristics if v.characteristic is not kind),
            CharacteristicValue.from_raw(kind, value),
        ),
    )
    if kind is Characteristic.WOUNDS:
        updated = replace(updated, starting_wounds=value, wounds_remaining=value)
    return updated


def replace_unit(state: GameState, unit: UnitInstance) -> None:
    state.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                unit if u.unit_instance_id == unit.unit_instance_id else u for u in a.units
            ),
        )
        for a in state.army_definitions
    ]
