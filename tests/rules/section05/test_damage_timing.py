"""FAQ48 post-save replacement and suffered damage even with no wound loss."""

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainSource,
    feel_no_pain_roll_spec,
    model_by_id,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.runtime_modifiers import (
    FailedSaveDamageReplacement,
    FailedSaveDamageReplacementBinding,
    FailedSaveDamageReplacementContext,
    RuntimeModifierRegistry,
)


def test_faq48_zero_replacement_after_save_keeps_resolve_damage_status(
    section05_definitions: Section02Definitions,
) -> None:
    state, target, sequence = native_sequence(section05_definitions)
    calls: list[FailedSaveDamageReplacementContext] = []

    def zero(
        context: FailedSaveDamageReplacementContext,
    ) -> FailedSaveDamageReplacement:
        calls.append(context)
        return FailedSaveDamageReplacement(
            source_id="constructed:s05:zero",
            source_unit_instance_id=target.unit_instance_id,
            replacement_damage=0,
        )

    registry = RuntimeModifierRegistry.from_bindings(
        failed_save_damage_replacement_bindings=(
            FailedSaveDamageReplacementBinding(
                "constructed:s05:zero", "constructed:s05:zero", zero
            ),
        )
    )
    decisions, remaining, status = resolve(
        state,
        sequence,
        fixed_sequence_dice(sequence, target, (6,), (6,), (1,)),
        registry=registry,
    )
    assert status is None
    assert remaining is None
    assert len(calls) == 1
    assert (
        model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds
        == target.own_models[0].current_wounds
    )
    events = decisions.event_log.records
    replacement = next(
        i for i, e in enumerate(events) if e.event_type == "failed_save_damage_replaced"
    )
    save = next(
        i
        for i, e in enumerate(events)
        if e.event_type == "dice_rolled"
        and isinstance(e.payload, dict)
        and isinstance(e.payload["spec"], dict)
        and str(e.payload["spec"]["roll_type"]).startswith("attack_sequence.save")
    )
    assert save < replacement
    assert (
        len([p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "damage"]) == 1
    )


@pytest.mark.parametrize("face", [1, 6])
def test_faq37_feel_no_pain_in_resolve_damage(
    section05_definitions: Section02Definitions, face: int
) -> None:
    state, target, sequence = native_sequence(section05_definitions)
    mid = target.own_model_ids()[0]
    source = FeelNoPainSource("constructed:s05:fnp", 5)
    state.record_model_feel_no_pain_sources(
        model_instance_id=mid, sources=(source,), decline_allowed=False
    )
    spec = feel_no_pain_roll_spec(
        source=source, player_id="opponent", model_instance_id=mid, wound_index=1
    )
    results = (
        *fixed_sequence_dice(sequence, target, (6,), (6,), (1,)),
        DiceRollManager("physical-fnp").roll_fixed(spec, (face,)).original_result,
    )
    decisions, remaining, status = resolve(state, sequence, results)
    assert remaining is None
    assert status is None
    rolls = payloads(decisions, "dice_rolled")
    assert [cast(dict[str, JsonValue], r["spec"])["roll_type"] for r in rolls] == [
        "attack_sequence.hit",
        "attack_sequence.wound",
        "attack_sequence.save.invulnerable",
        "attack_sequence.feel_no_pain",
    ]
    damage = next(p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "damage")
    fnp = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], damage["payload"])["feel_no_pain"],
    )
    assert fnp["requested_wounds"] == 1
    assert fnp["ignored_wounds"] == int(face == 6)
    assert model_by_id(state=state, model_instance_id=mid).current_wounds == target.own_models[
        0
    ].current_wounds - int(face == 1)
