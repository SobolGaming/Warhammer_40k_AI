"""Fresh mutable battle, decision, health, history and placement graphs."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import choose, pending
from tests.support.section10_fixtures import case, declaration_request


def test_one_case_cannot_consume_or_mutate_another_case(
    section10_definitions: Section02Definitions,
) -> None:
    left, ls, lu = case(section10_definitions)
    right, rs, ru = case(section10_definitions)
    before = right.lifecycle.to_payload()
    declaration_request(left, lu, "normal")
    assert ls.shooting_phase_state is not None
    assert ls.shooting_phase_state.selected_unit_ids == (lu.unit_instance_id,)
    assert right.lifecycle.to_payload() == before
    assert lu is not ru
    assert lu.own_models[0] is not ru.own_models[0]
    assert ls.army_definitions is not rs.army_definitions
    assert ls.battlefield_state is not rs.battlefield_state
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model

    apply_damage_to_model(
        state=ls,
        target_unit_instance_id=lu.unit_instance_id,
        model_instance_id=lu.own_model_ids()[0],
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    assert right.lifecycle.to_payload() == before
    assert ru.own_models[0].current_wounds == ru.own_models[0].initial_wounds
    choose(right, pending(right), ru.unit_instance_id)
    assert pending(right).decision_type == "select_shooting_type"
