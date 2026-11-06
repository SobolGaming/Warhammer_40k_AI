"""A real native model reaches the shared Damaged Hit resolver threshold."""

from dataclasses import replace
from pathlib import Path
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


@pytest.mark.parametrize("remaining_wounds", [1, 6, 7, 8, 20])
@pytest.mark.parametrize("phase_name", ["shooting", "fight"])
def test_native_belakor_damage_generated_threshold_and_restoration(
    selected_army_source_index: Path | None, remaining_wounds: int, phase_name: str
) -> None:
    import json

    from tests.daemons_native_source_helpers import damaged_state, native_definitions
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext
    from warhammer40k_core.engine.unit_factory import UnitInstance

    d = native_definitions(selected_army_source_index)
    phase = BattlePhase(phase_name)
    state = damaged_state(d, remaining_wounds, phase)
    state = GameState.from_payload(json.loads(json.dumps(state.to_payload())))
    own = unit_by_id(state=state, unit_instance_id="section02:subject")
    assert UnitInstance.from_payload(json.loads(json.dumps(own.to_payload()))) == own
    assert own.own_models[0].wounds_remaining == remaining_wounds
    (effect,) = own.damaged_effects
    assert (effect.damaged_effect_id, effect.wounds_min, effect.wounds_max, effect.modifier) == (
        "000001148:damaged:001",
        1,
        7,
        -1,
    )
    registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=catalog_damaged_effect_hit_roll_modifier_bindings(
            armies=tuple(state.army_definitions)
        )
    )
    weapon = d.weapon(
        "000001148:the-blade-of-shadows"
        if phase is BattlePhase.FIGHT
        else "000001148:betraying-shades"
    )
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=own.unit_instance_id,
        attacker_model_instance_id=own.own_model_ids()[0],
        target_unit_instance_id="enemy:target",
        weapon_profile=weapon,
        source_phase=phase,
    )
    assert registry.hit_roll_modifier(context) == (-1 if remaining_wounds <= 7 else 0)


@pytest.mark.parametrize(
    ("phase_name", "ignore", "seed"),
    [("fight", False, 0), ("shooting", False, 0), ("shooting", True, 1)],
)
def test_native_belakor_actual_attack_damaged_psychic_choice_component_restore(
    selected_army_source_index: Path | None,
    phase_name: str,
    ignore: bool,
    seed: int,
) -> None:
    from tests.daemons_native_source_helpers import native_definitions, resolve_native_attack
    from warhammer40k_core.core.dice import DiceRollResult, DiceRollResultPayload
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.phase import BattlePhase

    d = native_definitions(selected_army_source_index)
    state, decisions, psychic_choices = resolve_native_attack(
        d, BattlePhase(phase_name), ignore=ignore, seed=seed, restore=True
    )
    uninterrupted_state, uninterrupted_decisions, uninterrupted_choices = resolve_native_attack(
        d, BattlePhase(phase_name), ignore=ignore, seed=seed, restore=False
    )
    assert canonical_json(state.to_payload()) == canonical_json(uninterrupted_state.to_payload())
    assert canonical_json(decisions.to_payload()) == canonical_json(
        uninterrupted_decisions.to_payload()
    )
    assert psychic_choices == uninterrupted_choices
    assert psychic_choices == (9 if phase_name == "shooting" else 0)
    events = decisions.event_log.records
    assert any(event.event_type == "attack_sequence_completed" for event in events)
    dice = [
        DiceRollResult.from_payload(cast(DiceRollResultPayload, e.payload))
        for e in events
        if e.event_type == "dice_rolled"
    ]
    assert dice
    assert all(roll.source == "rng" for roll in dice)
    assert len({roll.roll_id for roll in dice}) == len(dice)
    assert DiceRollManager(
        state.private_rng_seed, event_log=decisions.event_log
    ).rng.to_payload() == (
        DiceRollManager(
            uninterrupted_state.private_rng_seed, event_log=uninterrupted_decisions.event_log
        ).rng.to_payload()
    )
    hits = [
        cast(dict[str, JsonValue], e.payload["payload"])
        for e in events
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "hit"
    ]
    assert len(hits) == (7 if phase_name == "fight" else 9)
    raw_twos = [hit for hit in hits if hit["unmodified_roll"] == 2]
    assert raw_twos
    for hit in raw_twos:
        assert hit["successful"] is ignore
        assert hit["final_roll"] == (2 if ignore else 1)
        roll_state = cast(dict[str, JsonValue], hit["roll_state"])
        original = cast(dict[str, JsonValue], roll_state["original_result"])
        assert original["source"] == "rng"
        assert original["values"] == [2]
    dice_by_id = {roll.roll_id: roll.to_payload() for roll in dice}
    for hit in hits:
        roll_state = cast(dict[str, JsonValue], hit["roll_state"])
        original = cast(dict[str, JsonValue], roll_state["original_result"])
        assert dice_by_id[cast(str, original["roll_id"])] == original
        assert hit["modifier"] == (0 if ignore else -1)
        assert hit["capped_modifier"] == (0 if ignore else -1)
        assert hit["target_number"] == 2
