"""Cached definitions cannot alias case-local model, effect, geometry or dice state."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    resolve,
)
from warhammer40k_core.engine.damage_allocation import model_by_id


def test_each_sequence_has_isolated_mutable_state(
    section05_definitions: Section02Definitions,
) -> None:
    first, target, sequence = native_sequence(section05_definitions)
    second, other, other_sequence = native_sequence(section05_definitions)
    before = second.to_payload()
    events, _, status = resolve(
        first, sequence, fixed_sequence_dice(sequence, target, (6,), (6,), (1,))
    )
    assert status is None
    assert events.event_log.records
    assert second.to_payload() == before
    assert (
        model_by_id(state=first, model_instance_id=target.own_model_ids()[0]).current_wounds
        == other.own_models[0].current_wounds - 1
    )
    assert first.army_definitions is not second.army_definitions
    assert first.persisting_effects is not second.persisting_effects
    assert first.battlefield_state is not second.battlefield_state
    assert target.own_models[0] is not other.own_models[0]
    assert sequence is not other_sequence
