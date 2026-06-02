from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
    CharacteristicValueKind,
    CharacteristicValuePayload,
    characteristic_from_token,
)
from warhammer40k_core.core.modifiers import (
    DamageCharacteristicResolution,
    Modifier,
    ModifierError,
    ModifierOperation,
    ModifierScope,
    ModifierStack,
    ModifierStackingError,
    ModifierStackPayload,
    ModifierTiming,
    modifier_operation_from_token,
    modifier_timing_from_token,
    resolve_characteristic_value,
    resolve_damage_characteristic,
)
from warhammer40k_core.rules.timing import ordered_modifier_timings


def test_initial_phase_two_characteristics_are_supported() -> None:
    assert tuple(characteristic.value for characteristic in Characteristic) == (
        "movement",
        "toughness",
        "save",
        "invulnerable_save",
        "wounds",
        "leadership",
        "objective_control",
        "weapon_skill",
        "ballistic_skill",
        "strength",
        "attacks",
        "armor_penetration",
        "damage",
        "range",
        "detection_range",
    )


def test_characteristic_values_expose_raw_base_and_final_values() -> None:
    value = CharacteristicValue.from_raw(Characteristic.MOVEMENT, 6)

    assert value.raw == 6
    assert value.base == 6
    assert value.final == 6
    assert value.applied_modifier_ids == ()


def test_characteristic_value_serialization_round_trips_exactly() -> None:
    value = CharacteristicValue(
        characteristic=Characteristic.ARMOR_PENETRATION,
        raw=-1,
        base=-1,
        final=-2,
        applied_modifier_ids=("storm-doctrine",),
    )
    payload = cast(
        CharacteristicValuePayload,
        json.loads(json.dumps(value.to_payload(), sort_keys=True)),
    )

    assert CharacteristicValue.from_payload(payload).to_payload() == value.to_payload()


def test_characteristic_values_reject_raw_strings_and_invalid_numbers() -> None:
    with pytest.raises(CharacteristicError):
        CharacteristicValue(
            characteristic=cast(Characteristic, "movement"),
            raw=6,
            base=6,
            final=6,
        )
    with pytest.raises(CharacteristicError):
        CharacteristicValue.from_raw(Characteristic.MOVEMENT, -1)
    with pytest.raises(CharacteristicError):
        CharacteristicValue.from_raw(Characteristic.MOVEMENT, cast(int, True))
    with pytest.raises(CharacteristicError):
        CharacteristicValue(
            characteristic=Characteristic.MOVEMENT,
            raw=6,
            base=6,
            final=6,
            applied_modifier_ids=("duplicate", "duplicate"),
        )
    with pytest.raises(CharacteristicError):
        characteristic_from_token("not-a-characteristic")


def test_phase14c_dash_characteristics_are_typed_and_replay_safe() -> None:
    source_dash = CharacteristicValue.source_dash(Characteristic.INVULNERABLE_SAVE)
    battle_shock_dash = CharacteristicValue.replacement_dash(
        Characteristic.OBJECTIVE_CONTROL,
        applied_modifier_ids=("battle_shock",),
    )

    assert source_dash.value_kind is CharacteristicValueKind.SOURCE_DASH
    assert source_dash.is_dash
    assert source_dash.to_payload()["value_kind"] == "source_dash"
    assert CharacteristicValue.from_payload(source_dash.to_payload()) == source_dash
    assert battle_shock_dash.value_kind is CharacteristicValueKind.REPLACEMENT_DASH
    assert battle_shock_dash.applied_modifier_ids == ("battle_shock",)
    assert battle_shock_dash.final == 0


def test_phase14c_dash_characteristics_reject_numeric_fields_and_modifiers() -> None:
    with pytest.raises(CharacteristicError):
        CharacteristicValue(
            characteristic=Characteristic.MOVEMENT,
            raw=0,
            base=0,
            final=1,
            value_kind=CharacteristicValueKind.SOURCE_DASH,
        )

    movement_bonus = Modifier(
        modifier_id="advance-bonus",
        scope=ModifierScope.for_characteristics((Characteristic.MOVEMENT,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
    )

    with pytest.raises(ModifierError):
        resolve_characteristic_value(
            CharacteristicValue.source_dash(Characteristic.MOVEMENT),
            (movement_bonus,),
        )


def test_phase14c_numeric_zero_characteristics_can_be_modified() -> None:
    objective_control_bonus = Modifier(
        modifier_id="banner-control",
        scope=ModifierScope.for_characteristics((Characteristic.OBJECTIVE_CONTROL,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
    )

    resolved = resolve_characteristic_value(
        CharacteristicValue.from_raw(Characteristic.OBJECTIVE_CONTROL, 0),
        (objective_control_bonus,),
    )

    assert resolved.value_kind is CharacteristicValueKind.NUMERIC
    assert resolved.raw == 0
    assert resolved.final == 1
    assert resolved.applied_modifier_ids == ("banner-control",)


def test_phase14c_detection_range_defaults_to_fifteen_and_can_be_lowered() -> None:
    detection_range = CharacteristicValue.detection_range_default()
    stealth_modifier = Modifier(
        modifier_id="stealth-field",
        scope=ModifierScope.for_characteristics((Characteristic.DETECTION_RANGE,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=-3,
    )

    resolved = resolve_characteristic_value(detection_range, (stealth_modifier,))

    assert detection_range.raw == 15
    assert resolved.final == 12
    assert resolved.applied_modifier_ids == ("stealth-field",)


def test_phase14c_damage_is_halved_after_other_modifiers() -> None:
    damage_bonus = Modifier(
        modifier_id="focused-strike",
        scope=ModifierScope.for_characteristics((Characteristic.DAMAGE,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=2,
    )

    resolved = resolve_damage_characteristic(
        CharacteristicValue.from_raw(Characteristic.DAMAGE, 5),
        (damage_bonus,),
        halve_damage_after_modifiers=True,
    )
    payload = resolved.to_payload()

    assert resolved.modifier_final == 7
    assert resolved.final == 4
    assert resolved.to_characteristic_value().final == 4
    assert DamageCharacteristicResolution.from_payload(payload).to_payload() == payload


def test_modifier_scope_matches_characteristic_and_target_explicitly() -> None:
    scope = ModifierScope.for_targets(
        ("unit-intercessors",),
        characteristics=(Characteristic.MOVEMENT,),
    )

    assert scope.matches(Characteristic.MOVEMENT, target_id="unit-intercessors")
    assert not scope.matches(Characteristic.TOUGHNESS, target_id="unit-intercessors")
    assert not scope.matches(Characteristic.MOVEMENT, target_id="unit-terminators")
    assert not scope.matches(Characteristic.MOVEMENT)


def test_modifier_scope_rejects_empty_or_untyped_inputs() -> None:
    with pytest.raises(ModifierError):
        ModifierScope.for_characteristics(())
    with pytest.raises(ModifierError):
        ModifierScope.for_targets(())
    with pytest.raises(ModifierError):
        ModifierScope.for_characteristics((cast(Characteristic, "movement"),))
    with pytest.raises(ModifierError):
        ModifierScope.for_targets((" ",))
    with pytest.raises(ModifierError):
        Modifier(
            modifier_id=" ",
            scope=ModifierScope.any(),
            timing=ModifierTiming.ADDITIVE,
            operation=ModifierOperation.ADD,
            operand=1,
        )
    with pytest.raises(ModifierError):
        ModifierStack(
            characteristic=Characteristic.MOVEMENT,
            raw_value=6,
            target_id=" ",
        )


def test_modifier_order_is_deterministic_and_values_are_inspectable() -> None:
    base_set = Modifier(
        modifier_id="set-mounted-move",
        scope=ModifierScope.for_characteristics((Characteristic.MOVEMENT,)),
        timing=ModifierTiming.BASE,
        operation=ModifierOperation.SET,
        operand=5,
        priority=20,
    )
    multiplier = Modifier(
        modifier_id="double-move",
        scope=ModifierScope.any(),
        timing=ModifierTiming.MULTIPLICATIVE,
        operation=ModifierOperation.MULTIPLY,
        operand=2,
        priority=10,
    )
    additive_low_priority = Modifier(
        modifier_id="advance-bonus",
        scope=ModifierScope.any(),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
        priority=30,
    )
    additive_high_priority = Modifier(
        modifier_id="aura-bonus",
        scope=ModifierScope.any(),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=2,
        priority=5,
    )
    ceiling = Modifier(
        modifier_id="max-move",
        scope=ModifierScope.any(),
        timing=ModifierTiming.FINAL,
        operation=ModifierOperation.CEILING,
        operand=12,
    )

    left = ModifierStack(
        characteristic=Characteristic.MOVEMENT,
        raw_value=6,
        modifiers=(additive_low_priority, ceiling, multiplier, base_set, additive_high_priority),
    )
    right = ModifierStack(
        characteristic=Characteristic.MOVEMENT,
        raw_value=6,
        modifiers=(ceiling, additive_high_priority, base_set, additive_low_priority, multiplier),
    )

    assert left.resolve().to_payload() == right.resolve().to_payload()
    assert left.resolve() == CharacteristicValue(
        characteristic=Characteristic.MOVEMENT,
        raw=6,
        base=5,
        final=12,
        applied_modifier_ids=(
            "set-mounted-move",
            "double-move",
            "aura-bonus",
            "advance-bonus",
            "max-move",
        ),
    )


def test_modifier_stack_ignores_non_matching_scopes() -> None:
    toughness_modifier = Modifier(
        modifier_id="toughness-bonus",
        scope=ModifierScope.for_characteristics((Characteristic.TOUGHNESS,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
    )
    other_target_modifier = Modifier(
        modifier_id="other-target-bonus",
        scope=ModifierScope.for_targets(("unit-terminators",)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=2,
    )
    matching_modifier = Modifier(
        modifier_id="matching-bonus",
        scope=ModifierScope.for_targets(("unit-intercessors",)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=3,
    )

    resolved = ModifierStack(
        characteristic=Characteristic.MOVEMENT,
        raw_value=6,
        target_id="unit-intercessors",
        modifiers=(toughness_modifier, other_target_modifier, matching_modifier),
    ).resolve()

    assert resolved.final == 9
    assert resolved.applied_modifier_ids == ("matching-bonus",)


def test_unsupported_modifier_stacking_fails_explicitly() -> None:
    first = Modifier(
        modifier_id="first-base",
        scope=ModifierScope.any(),
        timing=ModifierTiming.BASE,
        operation=ModifierOperation.SET,
        operand=5,
    )
    second = Modifier(
        modifier_id="second-base",
        scope=ModifierScope.any(),
        timing=ModifierTiming.BASE,
        operation=ModifierOperation.SET,
        operand=7,
    )

    with pytest.raises(ModifierStackingError):
        ModifierStack(
            characteristic=Characteristic.MOVEMENT,
            raw_value=6,
            modifiers=(first, second),
        ).resolve()


def test_exclusive_modifier_groups_fail_explicitly() -> None:
    first = Modifier(
        modifier_id="first-aura",
        scope=ModifierScope.any(),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
        exclusive_group="captain-aura",
    )
    second = Modifier(
        modifier_id="second-aura",
        scope=ModifierScope.any(),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
        exclusive_group="captain-aura",
    )

    with pytest.raises(ModifierStackingError):
        ModifierStack(
            characteristic=Characteristic.ATTACKS,
            raw_value=2,
            modifiers=(first, second),
        ).resolve()


def test_modifier_definition_errors_are_fail_fast() -> None:
    with pytest.raises(ModifierError):
        Modifier(
            modifier_id="bad-timing",
            scope=ModifierScope.any(),
            timing=ModifierTiming.ADDITIVE,
            operation=ModifierOperation.MULTIPLY,
            operand=2,
        )
    with pytest.raises(ModifierError):
        Modifier(
            modifier_id="bad-zero-multiply",
            scope=ModifierScope.any(),
            timing=ModifierTiming.MULTIPLICATIVE,
            operation=ModifierOperation.MULTIPLY,
            operand=0,
        )
    with pytest.raises(ModifierError):
        Modifier(
            modifier_id="bad-raw-operation",
            scope=ModifierScope.any(),
            timing=ModifierTiming.ADDITIVE,
            operation=cast(ModifierOperation, "add"),
            operand=1,
        )
    with pytest.raises(ModifierStackingError):
        ModifierStack(
            characteristic=Characteristic.MOVEMENT,
            raw_value=6,
            modifiers=(
                Modifier(
                    modifier_id="duplicate",
                    scope=ModifierScope.any(),
                    timing=ModifierTiming.ADDITIVE,
                    operation=ModifierOperation.ADD,
                    operand=1,
                ),
                Modifier(
                    modifier_id="duplicate",
                    scope=ModifierScope.any(),
                    timing=ModifierTiming.ADDITIVE,
                    operation=ModifierOperation.ADD,
                    operand=2,
                ),
            ),
        )
    with pytest.raises(ModifierError):
        modifier_timing_from_token("not-a-timing")
    with pytest.raises(ModifierError):
        modifier_operation_from_token("not-an-operation")


def test_modifier_stack_serialization_round_trips_exactly() -> None:
    stack = ModifierStack(
        characteristic=Characteristic.ARMOR_PENETRATION,
        raw_value=-1,
        target_id="weapon-bolt-rifle",
        modifiers=(
            Modifier(
                modifier_id="storm-doctrine",
                source_id="detachment-rule",
                scope=ModifierScope.for_targets(
                    ("weapon-bolt-rifle",),
                    characteristics=(Characteristic.ARMOR_PENETRATION,),
                ),
                timing=ModifierTiming.ADDITIVE,
                operation=ModifierOperation.ADD,
                operand=-1,
                priority=10,
                exclusive_group="doctrine",
            ),
        ),
    )
    payload = cast(
        ModifierStackPayload,
        json.loads(json.dumps(stack.to_payload(), sort_keys=True)),
    )

    assert ModifierStack.from_payload(payload).to_payload() == stack.to_payload()
    assert ModifierStack.from_payload(payload).resolve().final == -2


def test_modifier_payload_rejects_unknown_tokens() -> None:
    modifier = Modifier(
        modifier_id="valid",
        scope=ModifierScope.any(),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=1,
    ).to_payload()
    modifier["timing"] = "unknown"

    with pytest.raises(ModifierError):
        Modifier.from_payload(modifier)


def test_rules_timing_exports_deterministic_modifier_timing_order() -> None:
    assert ordered_modifier_timings() == (
        ModifierTiming.BASE,
        ModifierTiming.MULTIPLICATIVE,
        ModifierTiming.ADDITIVE,
        ModifierTiming.FINAL,
    )
