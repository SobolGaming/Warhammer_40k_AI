"""A real native model reaches the shared Damaged Hit resolver threshold."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_sequence import fixed_sequence_dice, native_sequence, payloads, resolve
from warhammer40k_core.core.datasheet import DamagedEffectDefinition, DamagedEffectKind
from warhammer40k_core.engine.damaged_effects import (
    catalog_damaged_effect_hit_roll_modifier_bindings,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@pytest.mark.parametrize("remaining_wounds", [2, 3, 4])
def test_damaged_threshold_changes_actual_hit_without_changing_native_weapon(
    section24_definitions: Section02Definitions, remaining_wounds: int
) -> None:
    state, target, sequence = native_sequence(section24_definitions)
    own = state.army_definitions[0].units[0]
    effect = DamagedEffectDefinition(
        damaged_effect_id="constructed:s24:damaged-three",
        model_profile_id=None,
        wounds_min=1,
        wounds_max=3,
        effect_kind=DamagedEffectKind.HIT_ROLL_MODIFIER,
        modifier=-1,
        source_id="constructed:s24:damaged",
    )
    own = replace(
        own,
        own_models=(replace(own.own_models[0], wounds_remaining=remaining_wounds),),
        damaged_effects=(effect,),
    )
    replace_unit(state, own)
    registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=catalog_damaged_effect_hit_roll_modifier_bindings(
            armies=tuple(state.army_definitions)
        )
    )
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, (2,), (1,), ()), registry=registry
    )
    assert remaining is None
    assert status is None
    (hit,) = [p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "hit"]
    result = cast(dict[str, JsonValue], hit["payload"])
    assert result["successful"] is (remaining_wounds > 3)
    assert sequence.attack_pools[0].weapon_profile.skill is not None
    assert sequence.attack_pools[0].weapon_profile.skill.final == 2
