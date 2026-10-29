"""Native model counts and wounds exercise the frozen strength predicate owner."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
)
from warhammer40k_core.engine.damage_allocation import (
    DamageKind,
    apply_damage_to_model,
    model_owner_player_id,
    unit_owner_player_id,
)
from warhammer40k_core.engine.unit_factory import UnitFactoryError
from warhammer40k_core.engine.unit_state import (
    BelowHalfStrengthContext,
    StartingStrengthRecord,
)


@pytest.mark.parametrize("datasheet", [INFRACTORS, LORD_EXULTANT])
def test_01_01_owner_and_nonempty_models(
    section01_definitions: Section02Definitions, datasheet: str
) -> None:
    unit = section01_definitions.unit(datasheet)
    state = minimal_state(section01_definitions, unit)
    assert unit_owner_player_id(state=state, unit_instance_id=unit.unit_instance_id) == "owner"
    assert {
        model_owner_player_id(state=state, model_instance_id=m.model_instance_id)
        for m in unit.own_models
    } == {"owner"}
    with pytest.raises(UnitFactoryError, match="own_models"):
        replace(unit, own_models=())


@pytest.mark.parametrize("remaining", range(6))
def test_01_02_01_multimodel_counts_not_wounds(
    section01_definitions: Section02Definitions, remaining: int
) -> None:
    unit = section01_definitions.unit()
    assert len(unit.own_models) == 5
    original = StartingStrengthRecord.from_unit(player_id="owner", unit=unit)
    damaged = replace(
        unit,
        own_models=tuple(
            replace(m, wounds_remaining=1 if i < remaining else 0)
            for i, m in enumerate(unit.own_models)
        ),
    )
    context = BelowHalfStrengthContext.from_unit(
        player_id="owner",
        unit=damaged,
        starting_strength=original,
        current_model_ids=tuple(m.model_instance_id for m in damaged.own_models if m.is_alive),
    )
    assert (
        context.is_below_starting_strength,
        context.is_at_half_strength,
        context.is_below_half_strength,
    ) == (remaining < 5, remaining * 2 == 5, remaining * 2 < 5)
    assert original.starting_model_count == 5


@pytest.mark.parametrize("remaining", range(6))
def test_01_02_01_singleton_uses_wounds(
    section01_definitions: Section02Definitions, remaining: int
) -> None:
    unit = section01_definitions.unit(LORD_EXULTANT)
    model = unit.own_models[0]
    assert model.initial_wounds == 5
    original = StartingStrengthRecord.from_unit(player_id="owner", unit=unit)
    damaged = replace(unit, own_models=(replace(model, wounds_remaining=remaining),))
    context = BelowHalfStrengthContext.from_unit(
        player_id="owner",
        unit=damaged,
        starting_strength=original,
        current_model_ids=(model.model_instance_id,) if remaining else (),
    )
    assert (
        context.is_below_starting_strength,
        context.is_at_half_strength,
        context.is_below_half_strength,
    ) == (remaining < 5, remaining * 2 == 5, remaining * 2 < 5)


def test_01_02_fresh_graphs_and_immutable_definitions(
    section01_definitions: Section02Definitions,
) -> None:
    first, second = section01_definitions.unit(), section01_definitions.unit()
    state = minimal_state(section01_definitions, first)
    model = first.own_models[0]
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=first.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=False,
    )
    assert state.army_definitions[0].units[0].own_models[0].current_wounds == 1
    assert (
        second.own_models[0].current_wounds
        == section01_definitions.unit().own_models[0].current_wounds
        == 2
    )
    first_payload = first.datasheet_abilities[0].rule_ir_payload
    second_payload = second.datasheet_abilities[0].rule_ir_payload
    fresh_payload = section01_definitions.unit().datasheet_abilities[0].rule_ir_payload
    assert first_payload is not None
    assert second_payload is not None
    assert fresh_payload is not None
    first_payload["section01-isolation"] = True
    assert "section01-isolation" not in second_payload
    assert "section01-isolation" not in fresh_payload
