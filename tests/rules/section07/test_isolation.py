"""Bounded fixture isolation evidence, distinct from universal order independence."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_state
from warhammer40k_core.engine.decision_controller import DecisionController


def test_native_mutable_graph_and_ability_payloads_do_not_leak_between_cases(
    section07_definitions: Section02Definitions,
) -> None:
    d = section07_definitions
    first = d.unit("000004078")
    second = d.unit("000004078")
    before = second.to_payload()
    ability = next(a for a in first.datasheet_abilities if a.rule_ir_payload is not None)
    assert ability.rule_ir_payload is not None
    ability.rule_ir_payload["constructed_isolation_probe"] = True
    assert second.to_payload() == before
    assert d.unit("000004078").to_payload() == before
    a = boundary_state(d)
    b = boundary_state(d)
    a.battle_shocked_unit_ids.append(a.army_definitions[0].units[0].unit_instance_id)
    assert b.battle_shocked_unit_ids == []
    assert (
        a.army_definitions[0].units[0].own_models[0]
        is not b.army_definitions[0].units[0].own_models[0]
    )
    left, right = DecisionController(), DecisionController()
    left.event_log.append("constructed_isolation_probe", {"value": 1})
    assert right.event_log.records == ()
