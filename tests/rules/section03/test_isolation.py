"""Shared indexed definitions never share a case's mutable wounds or rule payloads."""

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import native_state
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule


def test_reused_native_definition_has_fresh_model_and_state_graphs(
    section03_definitions: Section02Definitions,
) -> None:
    first = section03_definitions.unit(CHAOS_SPAWN)
    second = section03_definitions.unit(CHAOS_SPAWN)
    before = second.to_payload()
    assert first is not second
    assert first.own_models[0] is not second.own_models[0]
    left = native_state(section03_definitions, first)
    right = native_state(section03_definitions, second)
    destroy_model_by_rule(
        state=left,
        model_instance_id=first.own_models[0].model_instance_id,
        remove_from_battlefield=False,
    )
    left.battle_shocked_unit_ids.append(first.unit_instance_id)
    assert second.to_payload() == before
    assert not right.battle_shocked_unit_ids
    assert left.battlefield_state is not right.battlefield_state
