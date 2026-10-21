"""Core attached-unit example over native bodies; no attachment permission is granted."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import (
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.phase import GameLifecycleStage
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    StartingStrengthRecord,
)
from warhammer40k_core.engine.unit_strength_inventory import (
    starting_strength_records_for_army,
)


@pytest.mark.parametrize("body_alive", [0, 1, 2, 3, 5])
def test_01_02_01_attached_initial_group_remains_frozen(
    section01_definitions: Section02Definitions, body_alive: int
) -> None:
    body = section01_definitions.unit(identity="body")
    leader = section01_definitions.unit(LORD_EXULTANT, identity="leader")
    state = minimal_state(section01_definitions, body, leader)
    formation = AttachedUnitFormation(
        "attached-unit:section02:core-example",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:core:01.02.01",
        attachment_source_ids=(leader.datasheet_abilities[-2].source_id,),
    )
    army = replace(state.army_definitions[0], attached_units=(formation,))
    state.army_definitions[:] = [army]
    state.starting_strength_records[:] = starting_strength_records_for_army(army)
    state.stage = GameLifecycleStage.SETUP
    state.enter_battle()
    original = state.starting_strength_record_for_unit(formation.attached_unit_instance_id)
    assert original.starting_model_count == 6
    damaged = replace(
        body,
        own_models=tuple(
            replace(m, wounds_remaining=m.initial_wounds if i < body_alive else 0)
            for i, m in enumerate(body.own_models)
        ),
    )
    state.army_definitions[:] = [replace(army, units=(damaged, leader))]
    view = rules_unit_view_by_id(state=state, unit_instance_id=formation.attached_unit_instance_id)
    assert len(view.own_models) == 6
    assert len(view.alive_models()) == body_alive + 1
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=view,
        starting_strength=original,
        current_model_ids=tuple(m.model_instance_id for m in view.alive_models()),
    )
    assert (
        context.is_below_starting_strength,
        context.is_at_half_strength,
        context.is_below_half_strength,
    ) == (body_alive < 5, body_alive == 2, body_alive < 2)
    assert state.starting_strength_record_for_unit(formation.attached_unit_instance_id) == original
    assert "CHARACTER" in view.keywords
    assert all("CHARACTER" not in m.keywords for m in body.own_models)


@pytest.mark.parametrize("wounds", [5, 6, 7, 12])
def test_01_02_01_native_even_wounds_half_boundary(
    section01_definitions: Section02Definitions, wounds: int
) -> None:
    unit = section01_definitions.unit(MAULERFIEND)
    assert unit.own_models[0].initial_wounds == 12
    record = StartingStrengthRecord.from_unit(player_id="owner", unit=unit)
    damaged = replace(unit, own_models=(replace(unit.own_models[0], wounds_remaining=wounds),))
    context = BelowHalfStrengthContext.from_unit(
        player_id="owner",
        unit=damaged,
        starting_strength=record,
        current_model_ids=unit.own_model_ids(),
    )
    assert (
        context.is_below_starting_strength,
        context.is_at_half_strength,
        context.is_below_half_strength,
    ) == (wounds < 12, wounds == 6, wounds < 6)
