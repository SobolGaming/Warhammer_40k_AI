"""Independent characteristic, AP and saving-throw operations for one save option."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import (
    ModifierOperation,
    ModifierTerm,
    RollModifier,
    RollModifierOperation,
)
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    RandomProfileValue,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.saves import SaveOption


def profile_trace_for_save(value: ProfileCharacteristicValue) -> CharacteristicModifierTrace | None:
    if isinstance(value, RandomProfileValue):
        return CharacteristicModifierTrace(value.characteristic, value.raw, value.modifiers)
    return value.modifier_trace


def save_roll_modifier(option: SaveOption) -> int:
    return sum(
        modifier.operand
        for modifier in (*option.inherent_roll_modifiers, *option.roll_modifiers)
        if modifier.modifier_id not in option.ignored_roll_modifier_ids
    )


def inherent_save_roll_modifiers(
    option: SaveOption,
    *,
    armor_penetration: int,
    cover_applied: bool,
) -> tuple[RollModifier, ...]:
    from warhammer40k_core.engine.saves import SaveKind

    if option.save_kind is SaveKind.INVULNERABLE:
        return ()
    if option.inherent_roll_modifiers:
        if len(option.inherent_roll_modifiers) != 2:
            raise GameLifecycleError("Armour saves require distinct AP and cover operations.")
        ap, cover = option.inherent_roll_modifiers
        return (replace(ap, operand=armor_penetration), replace(cover, operand=int(cover_applied)))
    return (
        RollModifier(
            "core:armor-penetration:saving-throw-ap",
            armor_penetration,
            source_id="core:armor-penetration",
        ),
        RollModifier(
            "benefit_of_cover:saving-throw", int(cover_applied), source_id="benefit_of_cover"
        ),
    )


def validate_save_operations(option: SaveOption) -> None:
    from warhammer40k_core.engine.saves import SaveKind, cover_applies_to_armour_save

    characteristic = (
        Characteristic.SAVE
        if option.save_kind is SaveKind.ARMOUR
        else Characteristic.INVULNERABLE_SAVE
    )
    for trace, expected_characteristic, expected_value in (
        (option.characteristic_trace, characteristic, option.characteristic_target_number),
        (
            option.armor_penetration_trace,
            Characteristic.ARMOR_PENETRATION,
            option.armor_penetration,
        ),
    ):
        if trace is not None and (
            type(trace) is not CharacteristicModifierTrace
            or trace.characteristic is not expected_characteristic
            or trace.resolve().final != expected_value
        ):
            raise GameLifecycleError("SaveOption characteristic trace arithmetic drifted.")
    if (
        type(option.roll_modifiers) is not tuple
        or type(option.inherent_roll_modifiers) is not tuple
        or any(
            type(modifier) is not RollModifier
            or modifier.source_id is None
            or modifier.operation is not RollModifierOperation.ADD
            for modifier in (*option.roll_modifiers, *option.inherent_roll_modifiers)
        )
    ):
        raise GameLifecycleError("SaveOption roll operations require source-linked additions.")
    expected_inherent = inherent_save_roll_modifiers(
        option,
        armor_penetration=option.armor_penetration,
        cover_applied=(
            option.save_kind is SaveKind.ARMOUR
            and cover_applies_to_armour_save(
                armor_save=option.characteristic_target_number,
                armor_penetration=option.armor_penetration,
                cover_result=option.cover_result,
            )
        ),
    )
    if expected_inherent != option.inherent_roll_modifiers:
        raise GameLifecycleError("SaveOption inherent roll arithmetic drifted.")
    if option.save_kind is SaveKind.ARMOUR:
        cover = expected_inherent[1]
        if option.cover_applied != (
            cover.operand == 1 and cover.modifier_id not in option.ignored_roll_modifier_ids
        ):
            raise GameLifecycleError("SaveOption cover application differs from selected source.")
    modifier_ids = tuple(
        modifier.modifier_id
        for modifier in (*option.roll_modifiers, *option.inherent_roll_modifiers)
    )
    if len(set(modifier_ids)) != len(modifier_ids):
        raise GameLifecycleError("SaveOption roll modifier IDs are duplicated.")
    ignored = option.ignored_roll_modifier_ids
    if (
        type(ignored) is not tuple
        or any(type(identifier) is not str for identifier in ignored)
        or len(set(ignored)) != len(ignored)
        or not set(ignored).issubset(modifier_ids)
    ):
        raise GameLifecycleError("SaveOption ignored roll modifier IDs are invalid.")
    expected = max(2, option.characteristic_target_number - save_roll_modifier(option))
    if option.target_number != expected:
        raise GameLifecycleError("SaveOption target arithmetic differs from its source operations.")


def save_option_with_characteristic_terms(
    option: SaveOption,
    *,
    characteristic: Characteristic,
    terms: tuple[ModifierTerm, ...],
    source_id: str,
    modifier_id: str,
) -> SaveOption:
    from warhammer40k_core.engine.saves import SaveKind, SaveOption

    if type(option) is not SaveOption:
        raise GameLifecycleError("Save characteristic operations require SaveOption.")
    expected = (
        Characteristic.SAVE
        if option.save_kind is SaveKind.ARMOUR
        else Characteristic.INVULNERABLE_SAVE
    )
    if characteristic not in (expected, Characteristic.ARMOR_PENETRATION):
        raise GameLifecycleError("Save operation characteristic does not match its option.")
    if (
        type(terms) is not tuple
        or not terms
        or any(type(term) is not ModifierTerm for term in terms)
    ):
        raise GameLifecycleError("Save characteristic operations require typed modifier terms.")
    is_ap = characteristic is Characteristic.ARMOR_PENETRATION
    trace = option.armor_penetration_trace if is_ap else option.characteristic_trace
    if trace is None:
        trace = CharacteristicModifierTrace(
            characteristic,
            option.armor_penetration if is_ap else option.characteristic_target_number,
            (),
        )
    trace = replace(
        trace,
        modifiers=(
            *trace.modifiers,
            *(
                term.bind(
                    modifier_id=modifier_id if index == 0 else f"{modifier_id}:operation:{index}",
                    source_id=source_id,
                    characteristic=characteristic,
                )
                for index, term in enumerate(terms)
            ),
        ),
    )
    return rebuild_save_option(
        option,
        characteristic_trace=option.characteristic_trace if is_ap else trace,
        armor_penetration_trace=trace if is_ap else option.armor_penetration_trace,
        roll_modifiers=option.roll_modifiers,
        ignored_roll_modifier_ids=option.ignored_roll_modifier_ids,
        source_rule_ids=tuple(sorted({*option.source_rule_ids, source_id})),
    )


def save_option_with_roll_modifier(option: SaveOption, modifier: RollModifier) -> SaveOption:
    if type(modifier) is not RollModifier or modifier.source_id is None:
        raise GameLifecycleError("Save roll operation requires a source-linked modifier.")
    return rebuild_save_option(
        option,
        characteristic_trace=option.characteristic_trace,
        armor_penetration_trace=option.armor_penetration_trace,
        roll_modifiers=(*option.roll_modifiers, modifier),
        ignored_roll_modifier_ids=option.ignored_roll_modifier_ids,
        source_rule_ids=tuple(sorted({*option.source_rule_ids, modifier.source_id})),
    )


def rebuild_save_option(
    option: SaveOption,
    *,
    characteristic_trace: CharacteristicModifierTrace | None,
    armor_penetration_trace: CharacteristicModifierTrace | None,
    roll_modifiers: tuple[RollModifier, ...],
    ignored_roll_modifier_ids: tuple[str, ...],
    source_rule_ids: tuple[str, ...],
) -> SaveOption:
    from warhammer40k_core.engine.saves import SaveKind, SaveOption, cover_applies_to_armour_save

    characteristic = (
        option.characteristic_target_number
        if characteristic_trace is None
        else characteristic_trace.resolve().final
    )
    ap = (
        option.armor_penetration
        if armor_penetration_trace is None
        else armor_penetration_trace.resolve().final
    )
    cover = option.save_kind is SaveKind.ARMOUR and cover_applies_to_armour_save(
        armor_save=characteristic,
        armor_penetration=ap,
        cover_result=option.cover_result,
    )
    inherent = inherent_save_roll_modifiers(option, armor_penetration=ap, cover_applied=cover)
    roll = sum(
        modifier.operand
        for modifier in (*inherent, *roll_modifiers)
        if modifier.modifier_id not in ignored_roll_modifier_ids
    )
    target = max(2, characteristic - roll)
    return SaveOption(
        save_kind=option.save_kind,
        target_number=target,
        characteristic_target_number=characteristic,
        armor_penetration=ap,
        cover_applied=cover and inherent[1].modifier_id not in ignored_roll_modifier_ids,
        cover_result=option.cover_result,
        source_rule_ids=source_rule_ids,
        characteristic_trace=characteristic_trace,
        armor_penetration_trace=armor_penetration_trace,
        roll_modifiers=roll_modifiers,
        inherent_roll_modifiers=inherent,
        ignored_roll_modifier_ids=ignored_roll_modifier_ids,
    )


def save_option_ignoring_modifiers(option: SaveOption, identifiers: tuple[str, ...]) -> SaveOption:
    traces = (option.characteristic_trace, option.armor_penetration_trace)
    known = {
        modifier.modifier_id
        for trace in traces
        if trace is not None
        for modifier in trace.modifiers
    }
    known.update(
        modifier.modifier_id
        for modifier in (*option.roll_modifiers, *option.inherent_roll_modifiers)
    )
    if (
        type(identifiers) is not tuple
        or any(type(identifier) is not str for identifier in identifiers)
        or len(set(identifiers)) != len(identifiers)
        or not set(identifiers).issubset(known)
    ):
        raise GameLifecycleError("Save ignored modifier IDs are unknown or duplicated.")
    selected = tuple(
        None
        if trace is None
        else replace(
            trace,
            ignored_modifier_ids=tuple(
                identifier
                for identifier in identifiers
                if identifier in {modifier.modifier_id for modifier in trace.modifiers}
            ),
        )
        for trace in traces
    )
    return rebuild_save_option(
        option,
        characteristic_trace=selected[0],
        armor_penetration_trace=selected[1],
        roll_modifiers=option.roll_modifiers,
        ignored_roll_modifier_ids=tuple(
            identifier
            for identifier in identifiers
            if identifier
            in {
                modifier.modifier_id
                for modifier in (*option.roll_modifiers, *option.inherent_roll_modifiers)
            }
        ),
        source_rule_ids=option.source_rule_ids,
    )


def save_options_with_invulnerable_characteristic(
    options: tuple[SaveOption, ...],
    *,
    target_number: int,
    source_id: str,
    only_if_better: bool,
) -> tuple[SaveOption, ...]:
    """Preserve previously collected source operations when an invulnerable save is granted."""
    from warhammer40k_core.engine.saves import SaveKind, SaveOption

    if type(target_number) is not int or not 2 <= target_number <= 6:
        raise GameLifecycleError("Invulnerable save grant must be 2-6.")
    invulnerable = tuple(option for option in options if option.save_kind is SaveKind.INVULNERABLE)
    if len(invulnerable) > 1:
        raise GameLifecycleError("Save options contain duplicate invulnerable characteristics.")
    if invulnerable:
        existing = invulnerable[0]
        replacement = save_option_with_characteristic_terms(
            existing,
            characteristic=Characteristic.INVULNERABLE_SAVE,
            terms=(
                ModifierTerm(
                    ModifierOperation.CEILING if only_if_better else ModifierOperation.SET,
                    target_number,
                ),
            ),
            source_id=source_id,
            modifier_id=f"{source_id}:invulnerable-save",
        )
    else:
        replacement = SaveOption(
            save_kind=SaveKind.INVULNERABLE,
            target_number=target_number,
            characteristic_target_number=target_number,
            armor_penetration=0,
            source_rule_ids=(source_id,),
        )
        if options:
            source = options[0]
            replacement = replace(replacement, armor_penetration=source.armor_penetration)
            replacement = rebuild_save_option(
                replacement,
                characteristic_trace=None,
                armor_penetration_trace=source.armor_penetration_trace,
                roll_modifiers=source.roll_modifiers,
                ignored_roll_modifier_ids=tuple(
                    identifier
                    for identifier in source.ignored_roll_modifier_ids
                    if identifier in {modifier.modifier_id for modifier in source.roll_modifiers}
                ),
                source_rule_ids=tuple(sorted({source_id, *source.source_rule_ids})),
            )
    return (
        *tuple(option for option in options if option.save_kind is not SaveKind.INVULNERABLE),
        replacement,
    )
