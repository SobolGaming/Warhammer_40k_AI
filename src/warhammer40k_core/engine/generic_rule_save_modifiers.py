from __future__ import annotations

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.saves import SaveOption


def generic_rule_save_options_with_invulnerable_save(
    options: tuple[SaveOption, ...], *, target_number: int, source_id: str
) -> tuple[SaveOption, ...]:
    from warhammer40k_core.engine.save_modifier_operations import (
        save_options_with_invulnerable_characteristic,
    )

    return save_options_with_invulnerable_characteristic(
        options,
        target_number=target_number,
        source_id=source_id,
        only_if_better=False,
    )


def generic_rule_save_option_with_roll_modifier(
    option: SaveOption,
    delta: int,
    source_id: str,
    *,
    modifier_id: str | None = None,
) -> SaveOption:
    from warhammer40k_core.engine.save_modifier_operations import save_option_with_roll_modifier

    return save_option_with_roll_modifier(
        option,
        RollModifier(
            f"{source_id}:save-roll" if modifier_id is None else modifier_id,
            delta,
            source_id=source_id,
        ),
    )


__all__ = (
    "generic_rule_save_option_with_roll_modifier",
    "generic_rule_save_options_with_invulnerable_save",
)
