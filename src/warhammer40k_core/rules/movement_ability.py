"""Typed, source-owned permissions and optional keywords for one move."""

from __future__ import annotations

import math

import msgspec


class MovementAbilityDescriptor(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    descriptor_id: str
    source_rule_id: str
    ability_ids: tuple[str, ...]
    activation_keyword: str
    movement_modes: tuple[str, ...]
    model_transit_excluded_keywords: tuple[str, ...]
    horizontal_terrain_transit_height_inches: float
    optional_move_keywords: tuple[str, ...]
    completion_roll_expression: str
    battle_shocked_roll_values: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.descriptor_id or not self.source_rule_id or not self.activation_keyword:
            raise ValueError("Movement ability requires source, descriptor and keyword identity.")
        for values in (
            self.ability_ids,
            self.movement_modes,
            self.model_transit_excluded_keywords,
            self.optional_move_keywords,
        ):
            if not values or len(set(values)) != len(values) or any(not value for value in values):
                raise ValueError("Movement ability inventories must be nonempty and unique.")
        if (
            not math.isfinite(self.horizontal_terrain_transit_height_inches)
            or self.horizontal_terrain_transit_height_inches < 0
        ):
            raise ValueError("Movement ability terrain height must be finite and nonnegative.")
        if (
            self.completion_roll_expression != "D6"
            or not self.battle_shocked_roll_values
            or any(
                type(value) is not int or not 1 <= value <= 6
                for value in self.battle_shocked_roll_values
            )
        ):
            raise ValueError("Movement ability requires supported completion dice semantics.")
