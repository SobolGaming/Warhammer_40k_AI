"""Fresh case graphs keep the reusable selected definitions unchanged."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import movement_case


def test_units_ability_payloads_health_and_phase_ledgers_are_fresh(
    section09_definitions: Section02Definitions,
) -> None:
    first, a, unit_a = movement_case(section09_definitions)
    second, b, unit_b = movement_case(section09_definitions)
    assert a.to_payload() == b.to_payload()
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model

    apply_damage_to_model(
        state=a,
        target_unit_instance_id=unit_a.unit_instance_id,
        model_instance_id=unit_a.own_models[0].model_instance_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    a.battle_shocked_unit_ids.append(unit_a.unit_instance_id)
    assert unit_b.own_models[0].current_wounds == unit_b.own_models[0].initial_wounds
    assert not b.battle_shocked_unit_ids
    assert first.lifecycle.decision_controller is not second.lifecycle.decision_controller
    assert a.army_definitions is not b.army_definitions
    assert unit_a is not unit_b
    assert unit_a.own_models[0] is not unit_b.own_models[0]
