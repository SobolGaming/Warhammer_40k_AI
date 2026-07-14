from __future__ import annotations

from collections.abc import Set

from warhammer40k_core.core.datasheet import (
    DatasheetWargearOptionEffect,
    WargearOptionEffectKind,
)


def validate_replace_wargear_effect_count(
    *,
    selection_wargear_ids: tuple[str, ...],
    effect: DatasheetWargearOptionEffect,
    option_effects: tuple[DatasheetWargearOptionEffect, ...],
    selected_for_profile: Set[str],
    error_type: type[ValueError],
) -> None:
    if effect.wargear_id not in selection_wargear_ids and any(
        candidate.kind is WargearOptionEffectKind.REPLACE_WARGEAR
        and candidate.replaced_wargear_id == effect.replaced_wargear_id
        and candidate.wargear_id in selection_wargear_ids
        for candidate in option_effects
    ):
        return
    if effect.model_count != 1:
        raise error_type(
            "WargearSelection structured wargear option replacement model count is unsupported."
        )
    if effect.replaced_wargear_id is None:
        raise error_type(
            "WargearSelection structured wargear option replacement target is missing."
        )
    if effect.replaced_wargear_id not in selected_for_profile:
        raise error_type(
            "WargearSelection structured wargear option replacement target is not selected."
        )
    selected_wargear_count = sum(
        1 for wargear_id in selection_wargear_ids if wargear_id == effect.wargear_id
    )
    if selected_wargear_count != effect.wargear_count:
        raise error_type(
            "WargearSelection does not satisfy a structured wargear option replacement count."
        )
