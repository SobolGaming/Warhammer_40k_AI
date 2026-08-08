from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.saves import SaveKind, SaveOption


def generic_rule_save_options_with_invulnerable_save(
    options: tuple[SaveOption, ...], *, target_number: int, source_id: str
) -> tuple[SaveOption, ...]:
    if target_number < 2 or target_number > 6:
        raise GameLifecycleError("Generic invulnerable save target must be 2-6.")
    replacement = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=target_number,
        characteristic_target_number=target_number,
        armor_penetration=0,
        source_rule_ids=(source_id,),
    )
    return (
        *tuple(option for option in options if option.save_kind is not SaveKind.INVULNERABLE),
        replacement,
    )


def generic_rule_save_option_with_roll_modifier(
    option: SaveOption,
    delta: int,
    source_id: str,
) -> SaveOption:
    if type(option) is not SaveOption:
        raise GameLifecycleError("Generic save modifier requires SaveOption.")
    modified_target = max(2, option.target_number - delta)
    modified_characteristic_target = max(2, option.characteristic_target_number - delta)
    source_ids = option.source_rule_ids
    if source_id not in source_ids:
        source_ids = tuple(sorted((*source_ids, source_id)))
    return replace(
        option,
        target_number=modified_target,
        characteristic_target_number=modified_characteristic_target,
        source_rule_ids=source_ids,
    )


__all__ = (
    "generic_rule_save_option_with_roll_modifier",
    "generic_rule_save_options_with_invulnerable_save",
)
