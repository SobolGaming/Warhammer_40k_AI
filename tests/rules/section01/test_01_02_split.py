"""Constructed split permission applied to unmodified native model inventories."""

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_splitting import build_split_army
from warhammer40k_core.engine.unit_strength_inventory import (
    starting_strength_records_for_army,
)


@pytest.mark.parametrize("membership", [(0, 2), (1, 3, 4)])
@pytest.mark.parametrize("specified", [None, (2, 3), (5, 5)])
def test_01_02_06_partition_membership_strength_and_single_split(
    section01_definitions: Section02Definitions,
    membership: tuple[int, ...],
    specified: tuple[int, int] | None,
) -> None:
    unit = section01_definitions.unit()
    state = minimal_state(section01_definitions, unit)
    army = state.army_definitions[0]
    chosen = tuple(unit.own_models[i].model_instance_id for i in membership)
    split = build_split_army(
        army=army,
        unit_instance_id=unit.unit_instance_id,
        first_model_ids=chosen,
        request_id="split-choice",
        source_id="constructed:01.02.06:permission",
        specified_strengths=(len(chosen), 5 - len(chosen)) if specified == (2, 3) else specified,
    )
    record = split.unit_splits[0]
    assert set(record.model_ids(0)) == set(chosen)
    assert set(record.model_ids(1)) == set(unit.own_model_ids()) - set(chosen)
    assert sorted(len(record.model_ids(i)) for i in (0, 1)) == [2, 3]
    assert {m.model_instance_id: m for u in split.units for m in u.own_models} == {
        m.model_instance_id: m for m in unit.own_models
    }
    records = {r.unit_instance_id: r for r in starting_strength_records_for_army(split)}
    assert [records[record.successor_id(i)].starting_model_count for i in (0, 1)] == [
        len(chosen),
        5 - len(chosen),
    ]
    with pytest.raises(GameLifecycleError, match="already been split"):
        build_split_army(
            army=split,
            unit_instance_id=record.successor_id(0),
            first_model_ids=chosen[:1],
            request_id="again",
            source_id="constructed:01.02.06:permission",
            specified_strengths=None,
        )
    assert army.units == (unit,)


def test_01_02_10_added_unit_freezes_strength_on_entry(
    section01_definitions: Section02Definitions,
) -> None:
    state = minimal_state(section01_definitions)
    unit = section01_definitions.unit(identity="reinforcement")
    record = state.add_unit_to_army(
        player_id="owner", unit=unit, source_id="constructed:01.02.10:add-permission"
    )
    assert record.starting_model_count == len(unit.own_models) == 5
    assert state.starting_strength_record_for_unit(unit.unit_instance_id) == record
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.add_unit_to_army(
            player_id="owner",
            unit=unit,
            source_id="constructed:01.02.10:add-permission",
        )
