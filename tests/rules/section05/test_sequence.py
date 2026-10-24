"""Gathered dice, low-to-high saves, attack termination and actual damage mutation."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_sequence import (
    fixed_sequence_dice,
    native_sequence,
    payloads,
    resolve,
)
from warhammer40k_core.engine.attack_completion_authority import (
    completed_attack_sequence,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.event_log import JsonValue


@pytest.mark.parametrize(
    ("hits", "wounds", "saves", "lost"),
    [
        ((1,), (), (), 0),
        ((6,), (1,), (), 0),
        ((6,), (6,), (6,), 0),
        ((6,), (6,), (1,), 1),
        ((6, 6, 6), (6, 6, 6), (6, 1, 2), 2),
    ],
)
def test_native_sequence_step_order_termination_and_damage(
    section05_definitions: Section02Definitions,
    hits: tuple[int, ...],
    wounds: tuple[int, ...],
    saves: tuple[int, ...],
    lost: int,
) -> None:
    state, target, sequence = native_sequence(section05_definitions, attacks=len(hits))
    decisions, remaining, status = resolve(
        state, sequence, fixed_sequence_dice(sequence, target, hits, wounds, saves)
    )
    assert status is None
    assert remaining is None
    assert completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id="s05"
    ).is_complete
    steps = payloads(decisions, "attack_sequence_step")
    names = [p["step"] for p in steps]
    assert names.count("hit") == len(hits)
    assert names.count("wound") == len(wounds)
    assert names.count("save") == len(saves)
    if wounds:
        assert max(i for i, n in enumerate(names) if n == "hit") < min(
            i for i, n in enumerate(names) if n == "wound"
        )
    if saves:
        assert max(i for i, n in enumerate(names) if n == "wound") < min(
            i for i, n in enumerate(names) if n == "save"
        )
    events = decisions.event_log.records
    for step, expected_count in (("hit", len(hits)), ("wound", len(wounds)), ("save", len(saves))):
        rolled = [
            i
            for i, e in enumerate(events)
            if e.event_type == "dice_rolled"
            and str(
                cast(dict[str, JsonValue], cast(dict[str, JsonValue], e.payload)["spec"])[
                    "roll_type"
                ]
            ).startswith(f"attack_sequence.{step}")
        ]
        resolved = [
            i
            for i, e in enumerate(events)
            if e.event_type == "attack_sequence_step"
            and cast(dict[str, JsonValue], e.payload)["step"] == step
        ]
        assert len(rolled) == expected_count
        if rolled:
            assert max(rolled) < min(resolved)
    save_rolls = [
        i
        for i, e in enumerate(events)
        if e.event_type == "dice_rolled"
        and str(
            cast(dict[str, JsonValue], cast(dict[str, JsonValue], e.payload)["spec"])["roll_type"]
        ).startswith("attack_sequence.save")
    ]
    applied = [
        i
        for i, e in enumerate(events)
        if e.event_type == "attack_sequence_step"
        and cast(dict[str, JsonValue], e.payload)["step"] == "damage"
        and cast(dict[str, JsonValue], cast(dict[str, JsonValue], e.payload)["payload"])[
            "damage_application"
        ]
        is not None
    ]
    assert len(applied) == lost
    if applied:
        assert max(save_rolls) < min(applied)
    assert (
        model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).current_wounds
        == target.own_models[0].current_wounds - lost
    )
    if len(saves) > 1:
        assert [p["attack_context_id"] for p in steps if p["step"] == "save"] == [
            "s05:pool-001:attack-002",
            "s05:pool-001:attack-003",
            "s05:pool-001:attack-001",
        ]


def test_target_destruction_discards_remaining_attacks(
    section05_definitions: Section02Definitions,
) -> None:
    state, target, sequence = native_sequence(section05_definitions, attacks=3)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(state, target)
    decisions, remaining, status = resolve(
        state,
        sequence,
        fixed_sequence_dice(sequence, target, (6, 6, 6), (6, 6, 6), (1, 1, 1)),
    )
    assert status is None
    assert remaining is None
    assert len(payloads(decisions, "model_destroyed")) == 1
    assert (
        len([p for p in payloads(decisions, "attack_sequence_step") if p["step"] == "damage"]) == 1
    )
    assert not model_by_id(state=state, model_instance_id=target.own_model_ids()[0]).is_alive
    assert completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id="s05"
    ).is_complete
